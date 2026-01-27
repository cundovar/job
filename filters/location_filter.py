"""
Geographic filtering for job locations.
"""
from __future__ import annotations

from typing import Dict, List


def filter_by_location(jobs: List[Dict], criteria: Dict) -> List[Dict]:
    location_cfg = criteria.get("location", {})
    accepted_zones = [z.lower() for z in location_cfg.get("accepted_zones", [])]
    remote_accepted = bool(location_cfg.get("remote_accepted", True))
    hybrid_accepted = bool(location_cfg.get("hybrid_accepted", True))

    filtered = []
    for job in jobs:
        location = (job.get("location") or "").lower()
        description = (job.get("description") or "").lower()
        text = f"{location} {description}"

        # Accepter si zone trouvée
        if any(zone in text for zone in accepted_zones):
            filtered.append(job)
            continue
        if remote_accepted and ("remote" in text or "télétravail" in text):
            filtered.append(job)
            continue
        if hybrid_accepted and ("hybride" in text or "hybrid" in text):
            filtered.append(job)
            continue
        # Accepter aussi si la location contient "france" ou est vide (on laisse le scoring trier)
        if not location or "france" in location:
            filtered.append(job)
    return filtered
