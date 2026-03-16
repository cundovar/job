"""
Keyword filtering for job titles and descriptions.
"""
from __future__ import annotations

import unicodedata
from typing import Dict, List


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _text(job: Dict) -> str:
    return _normalize(f"{job.get('title','')} {job.get('description','')}")


def _title(job: Dict) -> str:
    return _normalize(job.get("title", ""))


def _red_flags(criteria: Dict) -> List[str]:
    red_flags_cfg = criteria.get("red_flags", {})
    keywords = red_flags_cfg.get("keywords", [])
    hard = red_flags_cfg.get("hard_exclude_keywords", [])
    hard_tech = red_flags_cfg.get("hard_exclude_keywords_tech", [])
    combined = [*keywords, *hard, *hard_tech]
    return [_normalize(kw) for kw in combined if isinstance(kw, str) and kw.strip()]


def _target_keyword_groups(criteria: Dict) -> List[List[str]]:
    groups: List[List[str]] = []
    for position in criteria.get("target_positions", []):
        keywords = [
            _normalize(kw)
            for kw in position.get("keywords", [])
            if isinstance(kw, str) and kw.strip()
        ]
        if keywords:
            groups.append(keywords)
    return groups


def filter_by_keywords(jobs: List[Dict], criteria: Dict) -> List[Dict]:
    red_flags = _red_flags(criteria)
    guard_cfg = criteria.get("red_flags", {})
    exclude_if = [_normalize(kw) for kw in guard_cfg.get("exclude_if_contains", [])]
    keep_if = [_normalize(kw) for kw in guard_cfg.get("keep_if_contains", [])]
    target_keyword_groups = _target_keyword_groups(criteria)

    filtered = []
    for job in jobs:
        text = _text(job)
        title = _title(job)
        # Exclure seulement les red flags (stage, alternance, etc.)
        if any(flag in text for flag in red_flags):
            continue
        if exclude_if and any(kw in text for kw in exclude_if):
            if keep_if and any(kw in text for kw in keep_if):
                filtered.append(job)
                continue
            continue

        if target_keyword_groups:
            title_matches = any(
                any(keyword in title for keyword in keywords)
                for keywords in target_keyword_groups
            )
            text_matches = max(
                (sum(1 for keyword in keywords if keyword in text) for keywords in target_keyword_groups),
                default=0,
            )
            if not title_matches and text_matches < 2:
                continue

        filtered.append(job)
    return filtered
