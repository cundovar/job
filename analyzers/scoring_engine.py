"""
Score jobs based on criteria weights.
"""
from __future__ import annotations

from typing import Dict, Tuple


def _detect_sector(job: Dict, criteria: Dict) -> Tuple[str, int]:
    text = f"{job.get('title','')} {job.get('description','')} {job.get('company','')}".lower()
    sectors = criteria.get("sectors", {})
    for sector_name, sector_cfg in sectors.items():
        for kw in sector_cfg.get("keywords", []):
            if kw.lower() in text:
                return sector_name, int(sector_cfg.get("score_weight", 0))
    return "unknown", 0


def _score_position(title: str, criteria: Dict, sector: str) -> int:
    title_l = title.lower()
    score = 0
    for position in criteria.get("target_positions", []):
        keywords = [kw.lower() for kw in position.get("keywords", [])]
        if any(kw in title_l for kw in keywords):
            # Respect sector restriction if present
            restriction = position.get("sector_restriction")
            if restriction and sector.lower() not in [s.lower() for s in restriction]:
                continue
            score = max(score, int(position.get("score_weight", 0)))
    return score


def _score_contract(job: Dict, criteria: Dict) -> int:
    contract = (job.get("contract_type") or "").lower()
    text = f"{contract} {job.get('description','')}".lower()
    best = 0
    for cfg in criteria.get("contracts", {}).get("accepted", []):
        ctype = cfg.get("type", "").lower()
        if ctype and (ctype in contract or ctype in text):
            best = max(best, int(cfg.get("score_weight", 0)))
    return best


def _score_location(job: Dict, criteria: Dict) -> int:
    location_cfg = criteria.get("location", {})
    weights = location_cfg.get("score_weights", {})
    text = f"{job.get('location','')} {job.get('description','')}".lower()

    if "pantin" in text:
        return int(weights.get("pantin", 0))
    if "paris" in text:
        return int(weights.get("paris", 0))
    if "île-de-france" in text or "ile-de-france" in text or "idf" in text:
        return int(weights.get("idf", 0))
    if "remote" in text or "télétravail" in text:
        return int(weights.get("remote", 0))
    if "hybrid" in text or "hybride" in text:
        return int(weights.get("hybrid", 0))
    return 0


def calculate_score(job: Dict, criteria: Dict) -> int:
    sector, sector_score = _detect_sector(job, criteria)
    job["sector"] = sector

    score = 0
    score += _score_position(job.get("title", ""), criteria, sector)
    score += sector_score
    score += _score_contract(job, criteria)
    score += _score_location(job, criteria)

    if job.get("salary"):
        score += int(criteria.get("scoring", {}).get("bonus_points", {}).get("salary_mentioned", 0))

    return min(score, 100)
