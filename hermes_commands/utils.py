"""
Shared helpers for Hermes-facing commands.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from agents import summarize_job
from applications import recommend_cv


def load_cached_jobs(path: str = "data/jobs_cache.json") -> List[Dict[str, Any]]:
    cache_path = Path(path)
    if not cache_path.exists():
        return []
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def ranked_jobs(jobs: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    return sorted(jobs, key=lambda job: int(job.get("score") or 0), reverse=True)[:limit]


def get_job_by_number(jobs: List[Dict[str, Any]], number: int) -> Dict[str, Any]:
    if number < 1 or number > len(jobs):
        raise IndexError(f"Offre {number} introuvable. Offres disponibles: {len(jobs)}")
    return jobs[number - 1]


def format_job_item(index: int, job: Dict[str, Any]) -> str:
    summary = summarize_job(job)
    cv = recommend_cv(job)
    return "\n".join(
        [
            f"{index}. {job.get('title', 'Poste non renseigne')} - {job.get('company', 'Entreprise non renseignee')}",
            f"Score : {job.get('score', 'Non renseigne')}/100",
            f"Lieu : {job.get('location', 'Non renseigne')}",
            f"Action : {summary.action}",
            f"CV conseille : {cv.cv_name}",
            f"URL : {job.get('url', 'Non renseignee')}",
        ]
    )


def format_job_list(jobs: List[Dict[str, Any]], title: str = "Offres") -> str:
    if not jobs:
        return f"{title}\n\nAucune offre disponible."

    blocks = [title, ""]
    for index, job in enumerate(jobs, start=1):
        blocks.append(format_job_item(index, job))
        blocks.append("")
    return "\n".join(blocks).rstrip()
