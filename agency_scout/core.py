"""Agency Scout — prospection d'agences en 4 étapes, sans magie.

1. Découverte : Google Places (Text Search, API New). Nom, adresse, coordonnées
   et site viennent de Google. Rien n'est déduit, l'IA ne cherche rien.
2. Fetch (requests) : page d'accueil + une page « contact / à propos », texte nettoyé,
   tronqué à ~3000 caractères.
3. Analyse : un appel LLM par domaine, sortie JSON validée par Pydantic,
   cache par empreinte du texte (pas de nouvel appel si le site n'a pas changé).
4. Stockage : SQLite (data/agency_scout.db), lu par l'API Node et par Hermes.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlparse
from urllib.error import HTTPError

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, ValidationError

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("AGENCY_SCOUT_DB", ROOT / "data" / "agency_scout.db"))

# Client Places partagé avec la V2 (tools/google_places.py) : un seul point
# d'accès HTTP, un seul masque de champs, une seule gestion de la pagination.
_TOOLS_DIR = ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from google_places import places_text_search, postal_code_of  # noqa: E402
from utils.email_protection import decode_protected_emails  # noqa: E402

# Centre par défaut : l'adresse de référence déjà utilisée par la V2 (Paris 20e).
DEFAULT_CENTER = tuple(float(x) for x in os.getenv("AGENCY_SCOUT_CENTER", "48.85536,2.39845").split(","))
DEFAULT_RADIUS_M = 3000
DEFAULT_QUERIES = ["agence web", "agence digitale", "création site internet", "organisme de formation numérique"]

# websiteUri place l'appel au palier « Text Search Enterprise » : 1000 appels
# gratuits/mois chez Google. Le plafond dur reste en dessous.
MONTHLY_CAP = int(os.getenv("AGENCY_SCOUT_MONTHLY_CAP", "900"))
MAX_PAGES_PER_QUERY = 3  # 20 résultats par page → 60 max par requête

TEXT_BUDGET = 3000
UA = "Mozilla/5.0 (compatible; AgencyScout/1.0; +https://varascundo.com)"
SECOND_PAGE_HINTS = ("contact", "cooperative", "a-propos", "apropos", "about", "qui-sommes", "agence", "equipe", "studio")


# ── Stockage ─────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS agencies (
  place_id TEXT PRIMARY KEY, name TEXT, address TEXT, lat REAL, lng REAL,
  distance_m INTEGER, website TEXT, domain TEXT, types TEXT, query TEXT,
  first_seen TEXT, last_seen TEXT, source TEXT DEFAULT 'places'
);
CREATE TABLE IF NOT EXISTS analyses (
  domain TEXT PRIMARY KEY, categorie TEXT, score INTEGER, resume TEXT, preuve TEXT,
  preuve_ok INTEGER, text_hash TEXT, model TEXT, error TEXT, analyzed_at TEXT,
  emails TEXT
);
CREATE TABLE IF NOT EXISTS usage (month TEXT PRIMARY KEY, calls INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA)
    # Migration des bases créées avant la colonne emails (décodage Cloudflare).
    cols = {row[1] for row in db.execute("PRAGMA table_info(analyses)")}
    if "emails" not in cols:
        db.execute("ALTER TABLE analyses ADD COLUMN emails TEXT")
        db.commit()
    # Migration des bases créées avant la saisie manuelle : tout ce qui s'y
    # trouve déjà vient de Google Places.
    cols = {row[1] for row in db.execute("PRAGMA table_info(agencies)")}
    if "source" not in cols:
        db.execute("ALTER TABLE agencies ADD COLUMN source TEXT DEFAULT 'places'")
        db.execute("UPDATE agencies SET source = 'places' WHERE source IS NULL")
        db.commit()
    return db


def set_meta(db, key: str, value) -> None:
    db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, json.dumps(value)))
    db.commit()


def get_meta(db, key: str, default=None):
    row = db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def structure_profile(domain: str, path: Path = DB_PATH) -> dict:
    """Profil auto-déclaré d'une structure, lu dans la base du scout.

    Lecture seule : catégorie (agence | formation | autre), résumé de
    l'auto-description du site et preuve citée. Retourne {} si le domaine est
    absent ou jamais analysé — aucune déduction depuis le nom ou l'URL.
    Utilisé par la voie spontanée pour donner aux rédacteurs (lettre, mail)
    le contexte « qu'est-ce que cette structure » avant d'écrire.
    """
    clean = str(domain or "").strip().lower()
    if not clean:
        return {}
    db = connect(path)
    try:
        row = db.execute(
            "SELECT categorie, score, resume, preuve FROM analyses WHERE domain = ?",
            (clean,),
        ).fetchone()
    finally:
        db.close()
    if row is None:
        return {}
    categorie = (row["categorie"] or "").strip()
    resume = (row["resume"] or "").strip()
    if not categorie and not resume:
        return {}
    return {
        "categorie": categorie,
        "score": row["score"],
        "resume": resume,
        "preuve": (row["preuve"] or "").strip(),
        "source": "agency_scout.db — auto-description du site, analyse du scout",
    }


# ── 1. Découverte Google Places ──────────────────────────────────────────────


class QuotaReached(RuntimeError):
    pass


def _count_call(db) -> None:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    row = db.execute("SELECT calls FROM usage WHERE month = ?", (month,)).fetchone()
    calls = row["calls"] if row else 0
    if calls >= MONTHLY_CAP:
        raise QuotaReached(f"Plafond mensuel Google Places atteint ({calls}/{MONTHLY_CAP} appels).")
    db.execute("INSERT OR REPLACE INTO usage VALUES (?, ?)", (month, calls + 1))
    db.commit()


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> int:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return round(6_371_000 * 2 * math.asin(math.sqrt(h)))


def search_places(db, query: str, center: tuple[float, float], radius_m: int, api_key: str) -> list[dict]:
    """Lieux bruts Places pour une requête ; chaque appel facturé passe dans le plafond."""
    try:
        return places_text_search(
            query,
            api_key,
            location_bias=(center[0], center[1], radius_m),
            page_size=20,
            max_pages=MAX_PAGES_PER_QUERY,
            on_request=lambda: _count_call(db),
        )
    except HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        raise RuntimeError(f"Google Places {exc.code} : {detail}") from exc


def domain_of(url: str | None) -> str | None:
    if not url:
        return None
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host or None


def discover(db, queries: list[str], center, radius_m: int, api_key: str,
             postal_codes: set[str] | None = None) -> list[str]:
    """Enregistre les lieux, renvoie leurs place_id.

    ``postal_codes`` inverse la règle d'admission : le code postal de l'adresse
    Google décide, le rayon ne filtre plus (il ne reste qu'un biais de
    recherche) — un 75020 à 3,2 km du centre reste dedans.
    """
    kept: list[str] = []
    for query in queries:
        for p in search_places(db, query, center, radius_m, api_key):
            loc = p.get("location") or {}
            if "latitude" not in loc:
                continue
            dist = haversine_m(center, (loc["latitude"], loc["longitude"]))
            if postal_codes:
                if postal_code_of(p) not in postal_codes:
                    continue  # le CP est la règle ; le voisinage est exclu même s'il est proche.
            elif dist > radius_m:  # locationBias favorise, ne filtre pas : on filtre ici.
                continue
            website = p.get("websiteUri")
            db.execute(
                """INSERT INTO agencies (place_id, name, address, lat, lng, distance_m, website,
                                         domain, types, query, first_seen, last_seen, source)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(place_id) DO UPDATE SET name=excluded.name, address=excluded.address,
                     lat=excluded.lat, lng=excluded.lng, distance_m=excluded.distance_m,
                     website=excluded.website, domain=excluded.domain, types=excluded.types,
                     last_seen=excluded.last_seen""",
                (p["id"], (p.get("displayName") or {}).get("text"), p.get("formattedAddress"),
                 loc["latitude"], loc["longitude"], dist, website, domain_of(website),
                 ",".join(p.get("types", [])), query, now(), now(), "places"),
            )
            kept.append(p["id"])
        db.commit()
    return list(dict.fromkeys(kept))


# ── 2. Fetch ─────────────────────────────────────────────────────────────────


def _clean(html: bytes) -> tuple[str, BeautifulSoup]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip(), soup


def _site_name(soup: BeautifulSoup) -> str:
    """Nom tel que le site se nomme lui-même — jamais déduit du domaine.

    `og:site_name` d'abord, sinon le `<title>`, dont on ne garde que ce qui
    précède le séparateur : « Studio Machin | Agence web à Paris » se lit
    « Studio Machin ».
    """
    tag = soup.find("meta", attrs={"property": "og:site_name"})
    candidate = str((tag.get("content") if tag else "") or "")
    if not candidate.strip() and soup.title and soup.title.string:
        candidate = str(soup.title.string)
    name = re.split(r"[|\u2013\u2014\u00b7\u00bb]", candidate)[0]
    return re.sub(r"\s+", " ", name).strip()[:80]


def fetch_site_text(url: str) -> tuple[str, list[str], list[str], str]:
    """Texte de l'accueil + d'une page secondaire, les URLs lues, les emails
    masqués décodés depuis le HTML brut (Cloudflare cfemail, mailto), et le nom
    que le site se donne."""
    with requests.Session() as client:
        client.headers["User-Agent"] = UA
        home = client.get(url, timeout=8)
        home.raise_for_status()
        home_text, soup = _clean(home.content)
        pages = [str(home.url)]
        html_pages = [home.text]
        second_text = ""
        base_host = urlparse(str(home.url)).netloc
        for a in soup.find_all("a", href=True):
            href = urljoin(str(home.url), a["href"])
            parsed = urlparse(href)
            if parsed.netloc == base_host and any(h in parsed.path.lower() for h in SECOND_PAGE_HINTS):
                try:
                    r = client.get(href, timeout=8)
                    if r.status_code == 200:
                        second_text = _clean(r.content)[0]
                        html_pages.append(r.text)
                        pages.append(str(r.url))
                except requests.RequestException:
                    pass
                break
    text = home_text[:1800] + ("\n---\n" + second_text[:1200] if second_text else "")
    emails = sorted({e for html in html_pages for e in decode_protected_emails(html)})
    return text[:TEXT_BUDGET], pages, emails, _site_name(soup)


# ── 3. Analyse LLM ───────────────────────────────────────────────────────────


class Verdict(BaseModel):
    categorie: Literal["agence", "formation", "autre"]
    score: int = Field(ge=0, le=10)
    resume: str = Field(max_length=400)
    preuve: str = Field(max_length=300)


SYSTEM_PROMPT = """Tu classes une structure à partir du SEUL texte de son site, et tu juges si un candidat a du sens à lui écrire.

Profil du candidat : {profile}

Règles :
- categorie : "agence" si elle produit des sites/applications pour des clients ; "formation" si c'est un organisme de formation ou d'accompagnement numérique ; sinon "autre".
- score : 0 à 10, pertinence d'une candidature spontanée pour CE profil (dev web / WordPress / intégration pour une agence ; formateur pour un organisme de formation).
- resume : 2 phrases max, ce que fait la structure et pourquoi le score.
- preuve : une phrase COPIÉE MOT POUR MOT du texte fourni qui justifie la catégorie.
- Si le texte est vide ou ne décrit pas l'activité : categorie "autre", score 0, et dis-le.

Réponds UNIQUEMENT avec ce JSON : {{"categorie": "...", "score": 0, "resume": "...", "preuve": "..."}}"""


def _profile_summary() -> str:
    try:
        import yaml
        p = yaml.safe_load((ROOT / "config" / "criteria.yaml").read_text(encoding="utf-8"))["user_profile"]
        return "; ".join(p.get("core_strengths", []))
    except Exception:  # noqa: BLE001
        return "développeur web full-stack (PHP/Symfony, React/Vue, WordPress) et ancien formateur web"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in s if not unicodedata.combining(c))).strip()


def _parse_json(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise ValueError("pas de JSON dans la réponse")
    return json.loads(match.group(0))


def llm_complete(system: str, user: str) -> tuple[dict, str]:
    """Route du rôle agency_fit (config/ai_role_routing.json), repli fournisseur par fournisseur."""
    from openai import OpenAI
    from utils.ai_role_routing import load_role_route

    providers = {"deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                 "glm": ("GLM_API_KEY", "GLM_BASE_URL", None)}
    errors = []
    for step in load_role_route("agency_fit"):
        if step.provider not in providers:
            continue
        key_env, base_env, default_base = providers[step.provider]
        key, base = os.getenv(key_env), os.getenv(base_env) or default_base
        if not key or not base or not step.model:
            errors.append(f"{step.provider}: non configuré")
            continue
        try:
            resp = OpenAI(api_key=key, base_url=base, timeout=60).chat.completions.create(
                model=step.model, temperature=0.1,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
            return _parse_json(resp.choices[0].message.content or ""), f"{step.provider}/{step.model}"
        except Exception as exc:  # noqa: BLE001 — on tente le fournisseur suivant
            errors.append(f"{step.provider}: {str(exc)[:120]}")
    raise RuntimeError("; ".join(errors) or "aucun fournisseur IA")


def analyze(domain: str, website: str, cached: sqlite3.Row | None, system: str) -> dict:
    """Fetch + LLM pour un domaine. Ne lève jamais : l'erreur est stockée."""
    try:
        text, pages, emails, _ = fetch_site_text(website)
    except Exception as exc:  # noqa: BLE001
        return {"domain": domain, "analyzed_at": now(), "error": f"site illisible : {str(exc)[:150]}"}
    return analyze_text(domain, text, pages, emails, cached, system)


def analyze_text(domain: str, text: str, pages: list[str], emails: list[str],
                 cached: sqlite3.Row | None, system: str) -> dict:
    """Le verdict IA sur un texte déjà lu. Aucune entrée/sortie réseau ici.

    Rend {} quand le texte n'a pas changé depuis la dernière analyse : le
    verdict précédent reste valable, aucun appel IA n'est dépensé.
    """
    base = {"domain": domain, "analyzed_at": now()}
    if len(text) < 80:
        return {**base, "error": "site sans texte exploitable (probablement tout en JavaScript)"}
    text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
    if cached and cached["text_hash"] == text_hash and not cached["error"]:
        return {}  # rien n'a changé : on garde l'analyse existante
    try:
        raw, model = llm_complete(system, f"Pages lues : {', '.join(pages)}\n\nTexte :\n{text}")
        v = Verdict.model_validate(raw)
    except (ValidationError, Exception) as exc:  # noqa: BLE001
        return {**base, "text_hash": text_hash, "emails": emails,
                "error": f"analyse IA invalide : {str(exc)[:150]}"}
    # Garde-fou anti-invention : la preuve doit exister dans le texte lu.
    preuve_ok = _norm(v.preuve)[:60] in _norm(text)
    return {**base, **v.model_dump(), "preuve_ok": int(preuve_ok), "text_hash": text_hash,
            "emails": emails, "model": model, "error": None}


def save_analysis(db, a: dict) -> None:
    cols = ["domain", "categorie", "score", "resume", "preuve", "preuve_ok", "text_hash", "model", "error", "analyzed_at", "emails"]
    row = [json.dumps(a.get("emails"), ensure_ascii=False) if c == "emails" and a.get("emails") is not None else a.get(c)
           for c in cols]
    db.execute(f"INSERT OR REPLACE INTO analyses ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", row)
    db.commit()


# ── Ajout manuel ─────────────────────────────────────────────────────────────

#: Hôtes que le serveur ne va pas chercher : l'URL vient du navigateur, et
#: c'est le serveur qui ouvre la connexion.
_PRIVATE_HOST = re.compile(
    r"^(localhost$|127\.|0\.|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.|\[?::1\]?$)",
    re.IGNORECASE,
)


def normalize_site_url(raw: str) -> str:
    """URL utilisable, ou une erreur qui dit ce qui cloche."""
    url = str(raw or "").strip()
    if not url:
        raise ValueError("URL vide.")
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Schéma non accepté : « {parsed.scheme} » — http ou https uniquement.")
    host = parsed.hostname or ""
    if not host or "." not in host or _PRIVATE_HOST.match(host):
        raise ValueError(f"Hôte non accepté : « {host or url} ».")
    return url


def add_agency(url: str, name: str | None = None, reanalyze: bool = False,
               path: Path = DB_PATH) -> dict:
    """Ajoute une structure à la main, à partir de l'URL de son site.

    Même trajet qu'un scan, moins la découverte Places : le site est lu une
    fois, l'IA rend le même verdict, la fiche rejoint la même base — et le
    bouton « Retenir & préparer » la trouve sans rien changer.

    Un site illisible ne fait pas échouer l'ajout : la fiche existe avec son
    erreur, et c'est l'utilisateur qui tranche.
    """
    site = normalize_site_url(url)
    domain = domain_of(site)
    if not domain:
        raise ValueError(f"Domaine illisible dans « {url} ».")

    db = connect(path)
    try:
        known = db.execute(
            "SELECT place_id, name, source FROM agencies WHERE domain = ?", (domain,)
        ).fetchone()
        if known and not reanalyze:
            # Déjà là : on ne crée pas un doublon et on ne réécrit pas une fiche
            # dont les données viennent peut-être de Google.
            return {"ok": True, "domain": domain, "name": known["name"], "already_known": True,
                    "source": known["source"] or "places", "analyzed": False,
                    "message": f"{domain} est déjà dans la base (source : {known['source'] or 'places'})."}

        try:
            text, pages, emails, site_name = fetch_site_text(site)
            fetch_error = None
        except Exception as exc:  # noqa: BLE001
            text, pages, emails, site_name = "", [site], [], ""
            fetch_error = f"site illisible : {str(exc)[:150]}"

        final_url = pages[0] if pages else site
        retenu = (name or "").strip() or site_name
        if not known:
            db.execute(
                """INSERT INTO agencies (place_id, name, address, lat, lng, distance_m, website,
                                         domain, types, query, first_seen, last_seen, source)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (f"manuel:{domain}", retenu, None, None, None, None, final_url, domain,
                 "", "saisie manuelle", now(), now(), "manuel"),
            )
        else:
            db.execute("UPDATE agencies SET last_seen = ? WHERE place_id = ?", (now(), known["place_id"]))
        db.commit()

        if fetch_error:
            save_analysis(db, {"domain": domain, "analyzed_at": now(), "error": fetch_error})
        else:
            cached = db.execute("SELECT * FROM analyses WHERE domain = ?", (domain,)).fetchone()
            verdict = analyze_text(domain, text, pages, emails,
                                   None if reanalyze else cached,
                                   SYSTEM_PROMPT.format(profile=_profile_summary()))
            if verdict:
                save_analysis(db, verdict)

        row = db.execute(
            "SELECT categorie, score, resume, error FROM analyses WHERE domain = ?", (domain,)
        ).fetchone()
        return {"ok": True, "domain": domain, "name": known["name"] if known else retenu,
                "website": final_url, "already_known": bool(known),
                "source": (known["source"] or "places") if known else "manuel",
                "analyzed": True,
                "categorie": row["categorie"] if row else None,
                "score": row["score"] if row else None,
                "resume": row["resume"] if row else None,
                "error": row["error"] if row else None}
    finally:
        db.close()


# ── Orchestration ────────────────────────────────────────────────────────────


def scan(queries: list[str] | None = None, center=DEFAULT_CENTER, radius_m: int = DEFAULT_RADIUS_M,
         reanalyze: bool = False, postal_codes: set[str] | None = None, log=print) -> dict:
    api_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GOOGLE_PLACES_API_KEY absente de l'environnement.")
    db = connect()
    running = get_meta(db, "running")
    if running and (datetime.now(timezone.utc) - datetime.fromisoformat(running["since"])).total_seconds() < 1800:
        raise RuntimeError(f"Un scan est déjà en cours depuis {running['since']}.")
    set_meta(db, "running", {"since": now(), "radius_m": radius_m, "center": list(center),
                             "postal_codes": sorted(postal_codes) if postal_codes else []})
    try:
        queries = queries or DEFAULT_QUERIES
        ids = discover(db, queries, center, radius_m, api_key, postal_codes=postal_codes)
        if postal_codes:
            log(f"{len(ids)} lieux — code postal imposé : {', '.join(sorted(postal_codes))}")
        else:
            log(f"{len(ids)} lieux dans le rayon de {radius_m} m")
        rows = db.execute(
            f"SELECT DISTINCT domain, website FROM agencies WHERE domain IS NOT NULL AND place_id IN ({','.join('?' * len(ids))})",
            ids).fetchall() if ids else []
        cached = {r["domain"]: r for r in db.execute("SELECT * FROM analyses")}
        system = SYSTEM_PROMPT.format(profile=_profile_summary())
        todo = [r for r in rows if reanalyze or r["domain"] not in cached or cached[r["domain"]]["error"]]
        log(f"{len(rows)} sites, {len(todo)} à analyser")
        with ThreadPoolExecutor(max_workers=6) as pool:
            for result in pool.map(lambda r: analyze(r["domain"], r["website"], cached.get(r["domain"]), system), todo):
                if result:
                    save_analysis(db, result)
                    log(f"  {result['domain']}: {result.get('categorie') or result.get('error')}")
        summary = {"finished_at": now(), "places": len(ids), "sites": len(rows), "analyzed": len(todo),
                   "radius_m": radius_m, "center": list(center), "queries": queries,
                   "postal_codes": sorted(postal_codes) if postal_codes else []}
        set_meta(db, "last_scan", summary)
        return summary
    finally:
        db.execute("DELETE FROM meta WHERE key = 'running'")
        db.commit()
        db.close()


def address_parts(address: str | None) -> tuple[str | None, str | None]:
    """Code postal et commune **lus** dans l'adresse Google, jamais déduits.

    « 10 rue X, 75020 Paris, France » → ("75020", "Paris"). Une fiche sans
    adresse rend (None, None) : elle ne se range dans aucun arrondissement, et
    c'est une information, pas un trou à combler.
    """
    match = re.search(r"\b(\d{5})\b[,\s]+([^,]+)", str(address or ""))
    if not match:
        return (None, None)
    return match.group(1), re.sub(r"\s+", " ", match.group(2)).strip() or None


def list_agencies(categorie: str | None = None, min_score: int = 0, path: Path = DB_PATH) -> dict:
    db = connect(path)
    sql = """SELECT a.place_id, a.name, a.address, a.distance_m, a.website, a.domain, a.lat, a.lng,
                    a.last_seen, COALESCE(a.source, 'places') AS source, n.categorie, n.score, n.resume, n.preuve, n.preuve_ok, n.error, n.analyzed_at,
                    n.emails
             FROM agencies a LEFT JOIN analyses n ON n.domain = a.domain
             WHERE COALESCE(n.score, 0) >= ?"""
    params: list = [min_score]
    if categorie:
        sql += " AND n.categorie = ?"
        params.append(categorie)
    sql += " ORDER BY COALESCE(n.score, -1) DESC, a.distance_m ASC"
    rows = [dict(r) for r in db.execute(sql, params)]
    for r in rows:
        try:
            r["emails"] = json.loads(r["emails"]) if r["emails"] else []
        except (TypeError, ValueError):
            r["emails"] = []
        # De quoi filtrer par arrondissement ou par commune sans que le front
        # ait à découper une adresse lui-même.
        r["code_postal"], r["ville"] = address_parts(r["address"])
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    usage = db.execute("SELECT calls FROM usage WHERE month = ?", (month,)).fetchone()
    out = {"agencies": rows, "running": get_meta(db, "running"), "last_scan": get_meta(db, "last_scan"),
           "places_calls_this_month": usage["calls"] if usage else 0, "places_monthly_cap": MONTHLY_CAP}
    db.close()
    return out


def start_background(args: list[str]) -> dict:
    """Lance `python3 -m agency_scout <args>` détaché ; rend la main tout de suite."""
    log_path = DB_PATH.with_suffix(".log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as log:
        proc = subprocess.Popen([sys.executable, "-m", "agency_scout", *args], cwd=ROOT,
                                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                start_new_session=True)
    return {"started": True, "pid": proc.pid, "log": str(log_path)}
