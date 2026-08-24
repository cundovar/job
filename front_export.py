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
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

FRONT_DATA_DIR = Path(__file__).resolve().parent / "front" / "public" / "data"

# Categorisation par mots-cles issus du profil utilisateur (config/criteria.yaml
# skills.backend / skills.frontend / core_strengths). Le front affiche tout ce
# qui ne matche aucune de ces trois categories sous "Nouvelles Portes".
CATEGORY_KEYWORDS = {
    "backend": [
        "php", "symfony", "node.js", "node ", "mysql", "mariadb",
        "backend", "back-end", "back end", "développeur api", "developpeur api",
    ],
    "frontend": [
        "react", "vue.js", "vuejs", "nuxt", "next.js", "javascript", "typescript",
        "frontend", "front-end", "front end",
    ],
    "webmaster_formateur": [
        "webmaster", "wordpress", "woocommerce", "formateur", "formatrice",
        "formation", "pédagogie", "pedagogie", "e-commerce",
    ],
}
CATCHALL_CATEGORY = "nouvelles_portes"
CATEGORY_ORDER = (*CATEGORY_KEYWORDS, CATCHALL_CATEGORY)


def _categorize(job: Dict[str, Any]) -> str:
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
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
        "published_at": job.get("scraped_at"),
        "url": job.get("url"),
        "ai_analysis": job.get("ai_analysis"),
    }


def _identity_part(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _job_key(job: Dict[str, Any]) -> str:
    url = _identity_part(job.get("url"))
    if url:
        return f"url:{url}"
    fields = "|".join(
        _identity_part(job.get(field))
        for field in ("title", "company", "location")
    )
    if fields.strip("|"):
        return f"fields:{fields}"
    return "payload:" + json.dumps(job, ensure_ascii=False, sort_keys=True, default=str)


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
) -> Dict[str, List[Dict[str, Any]]]:
    merged: Dict[str, tuple[str, Dict[str, Any]]] = {}
    for category, existing_jobs in _load_existing_buckets(search_dir).items():
        for job in existing_jobs:
            merged[_job_key(job)] = (category, job)

    # Les donnees du nouveau run remplacent la version precedente d'une meme
    # offre, sans supprimer les autres offres deja trouvees dans la journee.
    for job in jobs:
        front_job = _job_for_front(job)
        merged[_job_key(front_job)] = (_categorize(job), front_job)

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

    buckets = _merge_daily_jobs(search_dir, jobs)
    for category in CATEGORY_ORDER:
        cat_jobs = buckets.get(category, [])
        (search_dir / f"{category}.json").write_text(
            json.dumps({"jobs": cat_jobs}, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    all_jobs = [job for category_jobs in buckets.values() for job in category_jobs]
    postuler = sum(1 for job in all_jobs if _recommendation(job) == "POSTULER")
    peut_etre = sum(1 for job in all_jobs if _recommendation(job) == "PEUT-ÊTRE")

    FRONT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    index_path = FRONT_DATA_DIR / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        index = {"searches": []}

    entry = {
        "id": search_id,
        "date": search_id,
        "total": len(all_jobs),
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
