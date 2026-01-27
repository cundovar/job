"""
Keyword filtering for job titles and descriptions.
"""
from __future__ import annotations

from typing import Dict, List


def _text(job: Dict) -> str:
    return f"{job.get('title','')} {job.get('description','')}".lower()


def _red_flags(criteria: Dict) -> List[str]:
    return [kw.lower() for kw in criteria.get("red_flags", {}).get("keywords", [])]


def filter_by_keywords(jobs: List[Dict], criteria: Dict) -> List[Dict]:
    red_flags = _red_flags(criteria)

    filtered = []
    for job in jobs:
        text = _text(job)
        # Exclure seulement les red flags (stage, alternance, etc.)
        if any(flag in text for flag in red_flags):
            continue
        filtered.append(job)
    return filtered
