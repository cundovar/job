"""
Filter jobs by accepted sectors based on keywords.
"""
from __future__ import annotations

from typing import Dict, List, Tuple


def _detect_sector(text: str, criteria: Dict) -> Tuple[str, bool]:
    sectors = criteria.get("sectors", {})
    for sector_name, sector_cfg in sectors.items():
        for kw in sector_cfg.get("keywords", []):
            if kw.lower() in text:
                return sector_name, True
    return "unknown", False


def filter_by_sector(jobs: List[Dict], criteria: Dict) -> List[Dict]:
    excluded = [s.lower() for s in criteria.get("red_flags", {}).get("sectors_to_exclude", [])]
    filtered = []
    for job in jobs:
        text = f"{job.get('title','')} {job.get('description','')} {job.get('company','')}".lower()
        # Exclure seulement les secteurs à exclure, laisser passer le reste
        if any(s in text for s in excluded):
            continue
        filtered.append(job)
    return filtered
