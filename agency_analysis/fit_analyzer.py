"""Analyse d'adéquation agence ↔ profil candidat (phase 2 du plan agences).

Le modèle ne juge qu'à partir des pages réellement crawlées et du profil
public de Cundo (`criteria.yaml → user_profile`). Python valide le contrat ;
toute sortie invalide ou indisponible devient `fit_status: review` — jamais un
texte inventé. Les analyses sont persistées par domaine + empreinte
(`data/agency_analyses.json`, hors Git, volume persistant en prod) et ne sont
jamais détruites : une empreinte qui change pousse l'ancienne analyse dans
l'historique, une agence absente d'un run conserve la sienne.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

PROMPT_VERSION = "2"

AGENCY_FIT_ROLE = "agency_fit"
CATEGORIES = ("agence", "formation")
CONFIDENCES = ("haute", "moyenne", "faible")

# bornes de coût : le lot est plafonné et l'IA ne voit que des candidats déjà
# dédoublonnés et écartés des plateformes/annuaires par le barème V2.
DEFAULT_MAX_CALLS = 15
DEFAULT_MIN_SCORE = 45
MAX_STRENGTHS = 6
MAX_PAGES_IN_PROMPT = 6
PAGE_EXCERPT_CHARS = 1200

SYSTEM_PROMPT = """Tu juges l'adéquation entre une structure (agence web ou organisme de formation) et le profil d'un candidat, à partir UNIQUEMENT des éléments fournis.

Règles absolues :
1. Chaque point fort et chaque point faible doit s'appuyer sur une preuve observable dans les pages fournies (tu cites l'URL de la page concernée dans evidence_urls).
2. Interdit d'affirmer quoi que ce soit sur la structure ou sur le candidat qui ne figure pas dans les entrées. Si les pages ne décrivent pas l'activité, dis-le dans fit_summary et mets confidence à "faible".
3. N'invente jamais d'adresse, d'email, de client, de projet ou d'offre d'emploi.
4. Adapte l'angle au category fourni : "agence" → développement / webmaster / intégration WordPress ; "formation" → formateur / RGAA / accompagnement pédagogique. Ne force JAMAIS un positionnement full-stack.
5. fit_score : entier 0-10 (0 = aucun sens de candidater, 10 = adéquation évidente). confidence : "haute", "moyenne" ou "faible" selon la quantité et la précision des preuves.
6. evidence_urls : uniquement des URLs présentes dans la liste "pages_fournies".

Réponds UNIQUEMENT avec cet objet JSON, sans markdown autour :
{"strengths": ["..."], "weaknesses": ["..."], "application_angle": "...", "fit_summary": "...", "fit_score": 0, "confidence": "moyenne", "category": "agence|formation", "evidence_urls": ["..."]}"""


# ── Entrées ──────────────────────────────────────────────────────────────────


def public_profile(criteria_path: Path) -> Dict[str, Any]:
    """Profil PUBLIC du candidat (criteria.yaml → user_profile).

    Le profil maître CV (data/cv_master_profile.json) n'est jamais lu ici :
    cette analyse n'a pas besoin du détail des expériences, et rien du profil
    ne doit être recopié tel quel dans les sorties.
    """
    import yaml  # import local : même dépendance que analyzers/ai_analyzer

    data = yaml.safe_load(Path(criteria_path).read_text(encoding="utf-8")) or {}
    return data.get("user_profile") or {}


def load_env_file(path) -> None:
    """Charge `Clé=valeur` d'un .env via os.environ.setdefault, sans l'imprimer.

    Stdlib uniquement : la V2 tourne sur l'interpréteur système, où
    python-dotenv n'est pas garanti. Seules les variables ABSENTES sont posées.
    """
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())
    except OSError:
        pass


def domain_from_website(website: str) -> str:
    """Domaine normalisé (clé de cache), stdlib uniquement.

    Volontairement local : `company_analysis.duplicate.domain_of` tirait bs4 via
    le __init__ du package, et une panne d'import faisait silencieusement
    tomber TOUTES les analyses en « domaine vide ». Même contrat : une URL sans
    domaine exploitable rend « » (on ne devine pas une clé).
    """
    if not website:
        return ""
    try:
        from urllib.parse import urlparse

        host = str(urlparse(str(website).strip()).netloc or "").split("@")[-1]
        host = host.split(":")[0].strip().lower().rstrip(".")
        if host.startswith("www."):
            host = host[4:]
        if "." not in host or " " in host or not host:
            return ""
        return host
    except Exception:  # noqa: BLE001 - le cache ne doit jamais planter le run
        return ""


def build_payload(agency: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Payload JSON autorisé : pages utiles + métadonnées + profil public."""
    pages: List[Dict[str, str]] = []
    for page in (agency.get("page_texts") or [])[:MAX_PAGES_IN_PROMPT]:
        url = str(page.get("url") or "")
        text = " ".join(str(page.get("text") or "").split())
        if url and text:
            pages.append({"url": url, "extrait": text[:PAGE_EXCERPT_CHARS]})
    return {
        "profil_candidat": profile,
        "structure": {
            "nom": agency.get("name"),
            "site": agency.get("website"),
            "category": agency.get("category"),
            "score_regles": agency.get("score"),
            "stack_detectee": agency.get("stack") or [],
            "adresse_publiee": agency.get("address"),
            "distance_m": agency.get("distance_m"),
            "resume_moteur": (agency.get("snippet") or "")[:300],
        },
        "pages_fournies": pages,
    }


def fingerprint(payload: Dict[str, Any]) -> str:
    """Empreinte stable du jugement : pages + profil + version du prompt."""
    canonical = json.dumps(
        {"prompt_version": PROMPT_VERSION, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Validation du contrat ────────────────────────────────────────────────────


def normalize_analysis(
    raw: Any,
    agency: Dict[str, Any],
    payload: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[str]]:
    """Valide/normalise la réponse du modèle. Retourne (analyse, problèmes).

    Une sortie incomplète ou mensongère ne produit JAMAIS un texte inventé :
    elle devient `fit_status: review` avec la liste des problèmes.
    """
    issues: List[str] = []
    if not isinstance(raw, dict):
        return _review_analysis(agency, ["la réponse IA n'est pas un objet JSON"]), issues

    allowed_urls = {page["url"] for page in payload["pages_fournies"]}

    def _str_list(value: Any, label: str) -> List[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            issues.append(f"{label}: liste attendue")
            return []
        items = [str(item).strip() for item in value if str(item).strip()]
        if len(items) > MAX_STRENGTHS:
            items = items[:MAX_STRENGTHS]
            issues.append(f"{label}: plafonné à {MAX_STRENGTHS}")
        return items

    strengths = _str_list(raw.get("strengths"), "strengths")
    weaknesses = _str_list(raw.get("weaknesses"), "weaknesses")
    fit_summary = str(raw.get("fit_summary") or "").strip()
    application_angle = str(raw.get("application_angle") or "").strip()

    fit_score = raw.get("fit_score")
    if isinstance(fit_score, bool) or not isinstance(fit_score, (int, float)):
        fit_score_value: int | None = None
        if fit_score is not None:
            issues.append("fit_score: entier attendu")
    else:
        fit_score_value = max(0, min(10, int(fit_score)))

    confidence = str(raw.get("confidence") or "").strip().lower()
    if confidence not in CONFIDENCES:
        if confidence:
            issues.append(f"confidence inconnue: {confidence}")
        confidence = ""

    # category : le pipeline est déterministe, le modèle ne fait pas loi.
    category = agency.get("category") if agency.get("category") in CATEGORIES else ""
    model_category = str(raw.get("category") or "").strip().lower()
    if model_category and model_category != category:
        issues.append(f"category modèle ({model_category}) ≠ pipeline ({category}) — pipeline retenu")

    evidence_urls = []
    for url in raw.get("evidence_urls") or []:
        url = str(url).strip()
        if not url:
            continue
        if url in allowed_urls:
            evidence_urls.append(url)
        else:
            issues.append(f"evidence_url hors des pages fournies: {url[:80]}")

    analysis: Dict[str, Any] = {
        "fit_status": "ok",
        "strengths": strengths,
        "weaknesses": weaknesses,
        "application_angle": application_angle,
        "fit_summary": fit_summary,
        "fit_score": fit_score_value,
        "confidence": confidence,
        "category": category,
        "evidence_urls": evidence_urls,
        "issues": issues,
    }
    if not fit_summary:
        issues.append("fit_summary absent")
    if not strengths and not weaknesses:
        issues.append("aucun point fort ni point faible")
    if not evidence_urls:
        issues.append("aucune preuve URL dans les pages fournies")
    if issues:
        analysis["fit_status"] = "review"
    return analysis, issues


def _review_analysis(agency: Dict[str, Any], issues: List[str]) -> Dict[str, Any]:
    return {
        "fit_status": "review",
        "strengths": [],
        "weaknesses": [],
        "application_angle": "",
        "fit_summary": "",
        "fit_score": None,
        "confidence": "",
        "category": agency.get("category") if agency.get("category") in CATEGORIES else "",
        "evidence_urls": [],
        "issues": issues,
    }


# ── Cache persistant (data/agency_analyses.json) ────────────────────────────


def empty_cache() -> Dict[str, Any]:
    return {"version": 1, "prompt_version": PROMPT_VERSION, "analyses": {}}


def load_cache(path: Path) -> Dict[str, Any]:
    """Lecture tolérante : un cache absent/corrompu repart vide, jamais en erreur."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty_cache()
    if not isinstance(data, dict) or not isinstance(data.get("analyses"), dict):
        return empty_cache()
    data.setdefault("version", 1)
    data.setdefault("prompt_version", PROMPT_VERSION)
    return data


def save_cache_atomic(path: Path, cache: Dict[str, Any]) -> None:
    """Écriture atomique (tmp + os.replace) : un run interrompu ne corrompt pas."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cache["updated_at"] = datetime.now().isoformat(timespec="seconds")
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(cache, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def cached_analysis(cache: Dict[str, Any], domain: str, fp: str) -> Dict[str, Any] | None:
    """Analyse en cache pour (domaine, empreinte) — sinon None."""
    entry = cache.get("analyses", {}).get(domain)
    if not isinstance(entry, dict) or entry.get("fingerprint") != fp:
        return None
    analysis = entry.get("analysis")
    return dict(analysis) if isinstance(analysis, dict) else None


def store_analysis(cache: Dict[str, Any], domain: str, fp: str, analysis: Dict[str, Any],
                   provider: str = "", model: str = "") -> None:
    """Écrit/met à jour une entrée. L'ancienne empreinte part en `history` (max 2),
    une agence absente d'un run n'est jamais touchée (on n'écrit que son domaine)."""
    entries = cache.setdefault("analyses", {})
    old = entries.get(domain)
    entry: Dict[str, Any] = {
        "fingerprint": fp,
        "status": analysis.get("fit_status", "review"),
        "analysis": analysis,
        "provider": provider,
        "model": model,
        "analyzed_at": datetime.now().isoformat(timespec="seconds"),
        "obsolete": False,
    }
    if isinstance(old, dict) and old.get("fingerprint") != fp:
        old["obsolete"] = True
        history = old.get("history") or []
        old.pop("history", None)
        entry["history"] = ([old] + history)[:2]
    entries[domain] = entry


# ── Analyse ──────────────────────────────────────────────────────────────────


def parse_json_loose(text: str) -> Dict[str, Any]:
    """JSON depuis une réponse modèle, même entourée de fences markdown."""
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


class RoleRoutingClient:
    """Client IA minimal, routé par `config/ai_role_routing.json`.

    Volontairement hors `cv_generator.ai_agents` : la chaîne CV importe
    reportlab/bs4, absents de l'interpréteur système qui fait tourner la
    prospection. Même contrat de routage (rôle → fournisseurs en repli), via
    le chargeur stdlib `utils.ai_role_routing`. Seuls les fournisseurs HTTP
    (deepseek, glm) sont gérés ici ; une route CLI est signalée puis passée.
    """

    _DEFAULTS = {
        "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        "glm": ("GLM_API_KEY", "GLM_BASE_URL", None),
    }

    def __init__(self, agent_name: str = AGENCY_FIT_ROLE) -> None:
        self.agent_name = agent_name

    def complete(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str, str]:
        from utils.ai_role_routing import load_role_route

        user_message = json.dumps(payload, ensure_ascii=False)
        errors: List[str] = []
        for step in load_role_route(self.agent_name):
            if step.provider not in self._DEFAULTS:
                errors.append(f"{step.provider}: fournisseur non HTTP ignoré")
                continue
            try:
                data = self._call_provider(step.provider, step.model, user_message)
            except Exception as exc:  # noqa: BLE001 - on tente le repli suivant
                errors.append(f"{step.provider}: {type(exc).__name__}: {str(exc)[:120]}")
                continue
            return data, step.provider, step.model or ""
        raise RuntimeError("tous les fournisseurs IA ont échoué (" + "; ".join(errors) + ")")

    def _call_provider(self, provider: str, model: str | None, user_message: str) -> Dict[str, Any]:
        key_env, base_env, default_base = self._DEFAULTS[provider]
        api_key = os.getenv(key_env, "").strip()
        if not api_key:
            raise RuntimeError(f"{key_env} absente")
        base_url = os.getenv(base_env, "").strip() or default_base
        if not base_url:
            raise RuntimeError(f"{base_env} absente (requis pour {provider})")
        if not model:
            raise RuntimeError("aucun modèle résolu par le routage")

        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url, timeout=90.0)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.2,
        )
        return parse_json_loose(response.choices[0].message.content or "")


class FitAnalyzer:
    """Exécute le lot d'analyses avec cache, plafond d'appels et statuts review."""

    def __init__(self, llm_client: Any | None = None,
                 complete: Callable[[Dict[str, Any]], Dict[str, Any]] | None = None) -> None:
        self._client = llm_client
        self._complete = complete
        self.calls = 0

    def _call(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str, str]:
        """Un appel IA routé. Retourne (data, provider, model)."""
        self.calls += 1
        if self._complete is not None:
            data = self._complete(payload)
            if not isinstance(data, dict):
                raise ValueError("sortie du modèle non JSON")
            return data, "test", ""
        if self._client is None:
            self._client = RoleRoutingClient()
        return self._client.complete(payload)

    def analyze_agency(self, agency: Dict[str, Any], profile: Dict[str, Any],
                       cache: Dict[str, Any]) -> Dict[str, Any]:
        """Analyse une structure : cache d'abord, IA sinon, review en dernier recours."""
        payload = build_payload(agency, profile)
        fp = fingerprint(payload)
        domain = domain_from_website(str(agency.get("website") or ""))

        hit = cached_analysis(cache, domain, fp) if domain else None
        if hit is not None:
            hit["cache"] = "hit"
            return hit

        analysis: Dict[str, Any]
        provider = model = ""
        try:
            raw, provider, model = self._call(payload)
            analysis, _ = normalize_analysis(raw, agency, payload)
        except Exception as exc:  # noqa: BLE001 - l'indisponibilité IA n'invente rien
            analysis = _review_analysis(agency, [f"IA indisponible: {type(exc).__name__}: {exc}"])

        analysis.update({
            "provider": provider,
            "model": model,
            "fingerprint": fp,
            "analyzed_at": datetime.now().isoformat(timespec="seconds"),
            "prompt_version": PROMPT_VERSION,
            "cache": "miss",
        })
        if domain:
            store_analysis(cache, domain, fp, analysis, provider, model)
        return analysis

    def analyze_batch(self, agencies: List[Dict[str, Any]], profile: Dict[str, Any],
                      cache: Dict[str, Any]) -> Dict[str, Any]:
        """Lot plafonné. Retourne les compteurs publiés dans le payload du run."""
        stats = {
            "eligible": len(agencies),
            "analyzed": 0,
            "cache_hits": 0,
            "review": 0,
            "calls": self.calls,
        }
        for agency in agencies:
            if self.calls >= DEFAULT_MAX_CALLS:
                stats["plafond_atteint"] = True
                break
            analysis = self.analyze_agency(agency, profile, cache)
            domain = domain_from_website(str(agency.get("website") or ""))
            if domain:
                agency["analysis"] = analysis
            if analysis.get("cache") == "hit":
                stats["cache_hits"] += 1
            else:
                stats["analyzed"] += 1
            if analysis.get("fit_status") != "ok":
                stats["review"] += 1
        stats["calls"] = self.calls
        return stats


# ── Archive Markdown ─────────────────────────────────────────────────────────


def write_archive_md(path: Path, agencies: List[Dict[str, Any]], stats: Dict[str, Any],
                     run_label: str) -> Path:
    """Archive horodatée lisible : le jugement survit aux runs et se relit sans le front."""
    lines: List[str] = [
        f"# Analyse d'adéquation agences — {run_label}",
        "",
        f"Généré : {datetime.now().isoformat(timespec='seconds')} · "
        f"lot: {stats.get('eligible', 0)} éligibles · "
        f"{stats.get('analyzed', 0)} analyses IA · {stats.get('cache_hits', 0)} cache · "
        f"{stats.get('review', 0)} review · {stats.get('calls', 0)} appels",
        "",
        "> Niveau recherche : chaque point cite sa preuve. Ceci n'est pas un constat vérifié —",
        "> le Vérificateur n'intervient qu'au « Retenir & préparer ».",
        "",
    ]
    for agency in agencies:
        analysis = agency.get("analysis")
        if not isinstance(analysis, dict):
            continue
        distance = agency.get("distance_m")
        dist = f"{int(distance) / 1000:.1f} km" if isinstance(distance, (int, float)) else "distance inconnue"
        lines += [
            f"## {agency.get('name')} — {agency.get('category', '?')} — {dist}",
            f"- Site : {agency.get('website')}",
            f"- Verdict : **{analysis.get('fit_status')}**"
            + (f" · score {analysis.get('fit_score')}/10 · confiance {analysis.get('confidence')}" if analysis.get("fit_status") == "ok" else ""),
            f"- Résumé : {analysis.get('fit_summary') or '—'}",
            f"- Angle : {analysis.get('application_angle') or '—'}",
        ]
        for label, key in ("Points forts", "strengths"), ("Points faibles", "weaknesses"):
            items = analysis.get(key) or []
            lines.append(f"- {label} : " + ("; ".join(items) if items else "—"))
        evidence = analysis.get("evidence_urls") or []
        lines.append(f"- Preuves : " + ("; ".join(evidence) if evidence else "—"))
        if analysis.get("issues"):
            lines.append(f"- Problèmes : {'; '.join(analysis['issues'])}")
        lines.append("")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
