"""
Keyword filtering for job titles and descriptions.
"""
from __future__ import annotations

from typing import Dict, List


def _text(job: Dict) -> str:
    return f"{job.get('title','')} {job.get('description','')}".lower()


def _red_flags(criteria: Dict) -> List[str]:
    red_flags_cfg = criteria.get("red_flags", {})
    keywords = red_flags_cfg.get("keywords", [])
    hard = red_flags_cfg.get("hard_exclude_keywords", [])
    hard_tech = red_flags_cfg.get("hard_exclude_keywords_tech", [])
    combined = [*keywords, *hard, *hard_tech]
    return [kw.lower() for kw in combined if isinstance(kw, str) and kw.strip()]


def filter_by_keywords(jobs: List[Dict], criteria: Dict) -> List[Dict]:
    red_flags = _red_flags(criteria)
    guard_cfg = criteria.get("red_flags", {})
    exclude_if = [kw.lower() for kw in guard_cfg.get("exclude_if_contains", [])]
    keep_if = [kw.lower() for kw in guard_cfg.get("keep_if_contains", [])]

    filtered = []
    for job in jobs:
        text = _text(job)
        # Exclure seulement les red flags (stage, alternance, etc.)
        if any(flag in text for flag in red_flags):
            continue
        if exclude_if and any(kw in text for kw in exclude_if):
            if keep_if and any(kw in text for kw in keep_if):
                filtered.append(job)
                continue
            continue
        filtered.append(job)
    return filtered
