"""
front_export.py — Transforme les jobs analyses (issus de run_job_search) en la
structure JSON attendue par front/public/data/ (index.json + un fichier par
recherche/categorie). Appele en fin de run_job_search(), quel que soit le
declencheur (bouton web, tool Hermes job_today, cron GitHub Actions).

Sans cet export, le pipeline ecrit bien data/jobs_cache.json mais le front ne
lit jamais ce fichier : il ne connait que front/public/data/*.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

FRONT_DATA_DIR = Path(__file__).resolve().parent / "front" / "public" / "data"

# Les categories sont explicites : "Nouvelles Portes" vise les postes hybrides
# et l'automatisation IA. Les offres inconnues ont leur propre onglet afin de ne
# plus mélanger des rôles développeur avec ces opportunités.
CATEGORY_KEYWORDS = {
    "webmaster_formateur": [
        "webmaster", "wordpress", "woocommerce", "formateur", "formatrice",
        "ingénieur pédagogique", "ingenieur pedagogique", "pédagogie", "pedagogie",
    ],
    "nouvelles_portes": [
        "ai ops automation", "ia ops automation", "ai automation", "ia automation",
        "automation engineer", "automation developer", "automation specialist",
        "n8n developer", "n8n", "workflow automation", "agent automation",
        "agents ia", "agent ia", "ai agent", "agents ai", "low-code", "low code",
        "no-code", "no code", "citizen developer", "ai operations", "ia operations",
        "growth engineer automation", "growth engineering automation",
        "power automate", "power apps", "power platform", "copilot studio", "dataverse",
        "prompt engineering", "claude code", "consultant ia", "consultant ai",
        "chatbot", "assistants ia", "assistant ia", "product owner", "amoa",
        "médiateur numérique", "mediateur numerique", "médiation numérique",
        "mediation numerique", "conseiller numérique", "conseiller numerique",
        "accessibilité numérique", "accessibilite numerique", "rgaa",
        "coordinateur numérique", "coordinateur numerique", "devrel",
        "technical writer",
    ],
    "frontend": [
        "react", "vue.js", "vuejs", "nuxt", "next.js", "javascript", "typescript",
        "frontend", "front-end", "front end",
    ],
    "backend": [
        "php", "symfony", "node.js", "node ", "mysql", "mariadb",
        "backend", "back-end", "back end", "développeur api", "developpeur api",
        "java", "python", ".net", "dotnet", "c#", "fullstack", "full-stack",
        "full stack", "software engineer", "software developer", "développeur",
        "developpeur", "developer", "devops",
    ],
}
CATCHALL_CATEGORY = "non_classees"
ALREADY_SEEN_CATEGORY = "deja_vues"
CATEGORY_ORDER = (*CATEGORY_KEYWORDS, CATCHALL_CATEGORY, ALREADY_SEEN_CATEGORY)

TRACKING_QUERY_KEYS = {
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source",
}


def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _matches_any(text: str, keywords: List[str]) -> bool:
    padded = f" {text} "
    return any(f" {_normalize_text(keyword)} " in padded for keyword in keywords)


def _categorize(job: Dict[str, Any]) -> str:
    # Le titre est beaucoup plus fiable que la description pour l'onglet front.
    # Exemple : une offre WordPress/PHP doit rester dans Web & Formateur, même si
    # la description contient aussi PHP ; une offre Symfony "e-commerce" ne doit
    # pas basculer webmaster juste à cause du contexte métier.
    title = _normalize_text(job.get("title", ""))
    text = _normalize_text(f"{job.get('title', '')} {job.get('description', '')}")
    for category, keywords in CATEGORY_KEYWORDS.items():
        if _matches_any(title, keywords):
            return category
    for category, keywords in CATEGORY_KEYWORDS.items():
        if _matches_any(text, keywords):
            return category
    return CATCHALL_CATEGORY


def _job_for_front(job: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": job.get("title"),
        "company": job.get("company"),
        "location": job.get("location"),
        "contract_type": job.get("contract_type"),
        "description": job.get("description"),
        "salary": job.get("salary"),
        "sector": job.get("sector"),
        "source": job.get("source"),
        "score": job.get("score"),
        "published_at": job.get("published_at") or job.get("scraped_at"),
        "scraped_at": job.get("scraped_at"),
        "url": job.get("url"),
        "ai_analysis": job.get("ai_analysis"),
    }


def _identity_part(value: Any) -> str:
    return _normalize_text(value)


def _canonical_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
        query = [
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.casefold().startswith("utm_")
            and key.casefold() not in TRACKING_QUERY_KEYS
        ]
        return urlunsplit(
            (
                parsed.scheme.casefold(),
                parsed.netloc.casefold(),
                parsed.path.rstrip("/"),
                urlencode(sorted(query)),
                "",
            )
        )
    except ValueError:
        return raw.casefold()


def _job_identity_keys(job: Dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    url = _canonical_url(job.get("url"))
    if url:
        keys.add(f"url:{url}")

    title = _identity_part(job.get("title"))
    company = _identity_part(job.get("company"))
    location = _identity_part(job.get("location"))
    if title and company:
        keys.add(f"role:{title}|{company}|{location}")
    return keys


def _job_key(job: Dict[str, Any]) -> str:
    identity_keys = _job_identity_keys(job)
    url_keys = sorted(key for key in identity_keys if key.startswith("url:"))
    if url_keys:
        return url_keys[0]
    role_keys = sorted(key for key in identity_keys if key.startswith("role:"))
    if role_keys:
        return role_keys[0]
    return "payload:" + json.dumps(job, ensure_ascii=False, sort_keys=True, default=str)


def _session_day(name: str) -> str | None:
    iso_match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", name)
    if iso_match:
        return "-".join(iso_match.groups())
    compact_match = re.match(r"^(\d{4})(\d{2})(\d{2})", name)
    if compact_match:
        return "-".join(compact_match.groups())
    return None


def _load_seen_keys(current_day: str) -> set[str]:
    seen: set[str] = set()
    if not FRONT_DATA_DIR.exists():
        return seen
    for session_dir in FRONT_DATA_DIR.iterdir():
        if not session_dir.is_dir():
            continue
        session_day = _session_day(session_dir.name)
        if not session_day or session_day == current_day:
            continue
        for category_path in session_dir.glob("*.json"):
            try:
                payload = json.loads(category_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
            if not isinstance(jobs, list):
                continue
            for job in jobs:
                if isinstance(job, dict):
                    seen.update(_job_identity_keys(job))
    return seen


def _load_existing_buckets(search_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for category in CATEGORY_ORDER:
        category_path = search_dir / f"{category}.json"
        try:
            payload = json.loads(category_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
        jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
        if isinstance(jobs, list):
            buckets[category] = [job for job in jobs if isinstance(job, dict)]
    return buckets


def _merge_daily_jobs(
    search_dir: Path,
    jobs: List[Dict[str, Any]],
    seen_keys: set[str] | None = None,
) -> Dict[str, List[Dict[str, Any]]]:
    seen_keys = seen_keys or set()
    merged: Dict[str, tuple[str, Dict[str, Any]]] = {}
    for category, existing_jobs in _load_existing_buckets(search_dir).items():
        for job in existing_jobs:
            merged[_job_key(job)] = (category, job)

    # Les donnees du nouveau run remplacent la version precedente d'une meme
    # offre, sans supprimer les autres offres deja trouvees dans la journee.
    for job in jobs:
        front_job = _job_for_front(job)
        already_seen = bool(_job_identity_keys(front_job) & seen_keys)
        category = ALREADY_SEEN_CATEGORY if already_seen else _categorize(job)
        merged[_job_key(front_job)] = (category, front_job)

    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for category, job in merged.values():
        buckets.setdefault(category, []).append(job)
    for category_jobs in buckets.values():
        category_jobs.sort(key=lambda item: item.get("score") or 0, reverse=True)
    return buckets


def _recommendation(job: Dict[str, Any]) -> str:
    analysis = job.get("ai_analysis")
    return analysis.get("recommandation", "") if isinstance(analysis, dict) else ""


def export_front_data(jobs: List[Dict[str, Any]], search_id: str | None = None) -> None:
    """Fusionne le run dans les resultats du jour et met a jour index.json."""
    if not jobs:
        return

    search_id = search_id or date.today().isoformat()
    search_dir = FRONT_DATA_DIR / search_id
    search_dir.mkdir(parents=True, exist_ok=True)

    current_day = _session_day(search_id) or date.today().isoformat()
    buckets = _merge_daily_jobs(search_dir, jobs, _load_seen_keys(current_day))
    for category in CATEGORY_ORDER:
        cat_jobs = buckets.get(category, [])
        (search_dir / f"{category}.json").write_text(
            json.dumps({"jobs": cat_jobs}, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    all_jobs = [job for category_jobs in buckets.values() for job in category_jobs]
    already_seen_jobs = buckets.get(ALREADY_SEEN_CATEGORY, [])
    new_jobs = [
        job
        for category, category_jobs in buckets.items()
        if category != ALREADY_SEEN_CATEGORY
        for job in category_jobs
    ]
    postuler = sum(1 for job in new_jobs if _recommendation(job) == "POSTULER")
    peut_etre = sum(1 for job in new_jobs if _recommendation(job) == "PEUT-ÊTRE")

    FRONT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    index_path = FRONT_DATA_DIR / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        index = {"searches": []}

    entry = {
        "id": search_id,
        "date": search_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(new_jobs),
        "found_total": len(all_jobs),
        "already_seen": len(already_seen_jobs),
        "postuler": postuler,
        "peut_etre": peut_etre,
        "categories": {
            category: {"count": len(category_jobs)}
            for category, category_jobs in buckets.items()
            if category_jobs
        },
    }
    # Une entree par jour, contenant le cumul deduplique de tous les runs.
    index["searches"] = [s for s in index.get("searches", []) if s.get("id") != search_id]
    index["searches"].insert(0, entry)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
