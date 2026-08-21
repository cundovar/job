"""
Geographic filtering for job locations.
"""
from __future__ import annotations

import unicodedata
from typing import Dict, List


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def filter_by_location(jobs: List[Dict], criteria: Dict) -> List[Dict]:
    location_cfg = criteria.get("location", {})
    accepted_zones = [_normalize(str(z)) for z in location_cfg.get("accepted_zones", [])]
    remote_accepted = bool(location_cfg.get("remote_accepted", True))
    hybrid_accepted = bool(location_cfg.get("hybrid_accepted", True))

    filtered = []
    for job in jobs:
        location = _normalize(str(job.get("location") or ""))
        description = _normalize(str(job.get("description") or ""))
        text = f"{location} {description}"

        # Accepter si une zone IDF configurée est trouvée.
        if any(zone in text for zone in accepted_zones):
            filtered.append(job)
            continue
        if remote_accepted and ("remote" in text or "teletravail" in text):
            filtered.append(job)
            continue
        if hybrid_accepted and ("hybride" in text or "hybrid" in text):
            filtered.append(job)
            continue
        # Accepter aussi si la location contient "france" ou est vide (on laisse le scoring trier)
        if not location or "france" in location:
            filtered.append(job)
    return filtered
