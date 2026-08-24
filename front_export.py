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
        "score": job.get("score"),
        "published_at": job.get("scraped_at"),
        "url": job.get("url"),
        "ai_analysis": job.get("ai_analysis"),
    }


def export_front_data(jobs: List[Dict[str, Any]], search_id: str | None = None) -> None:
    """Ecrit front/public/data/{search_id}/{categorie}.json et met a jour index.json."""
    if not jobs:
        return

    search_id = search_id or date.today().isoformat()
    search_dir = FRONT_DATA_DIR / search_id
    search_dir.mkdir(parents=True, exist_ok=True)

    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for job in jobs:
        buckets.setdefault(_categorize(job), []).append(_job_for_front(job))

    for category, cat_jobs in buckets.items():
        cat_jobs.sort(key=lambda j: j.get("score") or 0, reverse=True)
        (search_dir / f"{category}.json").write_text(
            json.dumps({"jobs": cat_jobs}, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    postuler = sum(1 for j in jobs if j.get("ai_analysis", {}).get("recommandation") == "POSTULER")
    peut_etre = sum(1 for j in jobs if j.get("ai_analysis", {}).get("recommandation") == "PEUT-ÊTRE")

    FRONT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    index_path = FRONT_DATA_DIR / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        index = {"searches": []}

    entry = {
        "id": search_id,
        "date": search_id,
        "total": len(jobs),
        "postuler": postuler,
        "peut_etre": peut_etre,
        "categories": {cat: {"count": len(cat_jobs)} for cat, cat_jobs in buckets.items()},
    }
    # Remplace l'entree du jour si elle existe deja (un run = ecrase le run precedent du meme jour)
    index["searches"] = [s for s in index.get("searches", []) if s.get("id") != search_id]
    index["searches"].insert(0, entry)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
