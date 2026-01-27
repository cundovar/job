"""
Filter jobs by accepted contract types and exclude rejected ones.
"""
from __future__ import annotations

from typing import Dict, List


def filter_by_contract(jobs: List[Dict], criteria: Dict) -> List[Dict]:
    contracts_cfg = criteria.get("contracts", {})
    rejected = [c.lower() for c in contracts_cfg.get("rejected", [])]

    filtered = []
    for job in jobs:
        text = f"{job.get('contract_type','')} {job.get('title','')} {job.get('description','')}".lower()

        # Exclure seulement les contrats rejetés (stage, alternance, etc.)
        if any(r in text for r in rejected):
            continue

        filtered.append(job)

    return filtered
