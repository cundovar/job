"""
Score jobs based on criteria weights.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Dict, Tuple


def _normalize(text: object) -> str:
    """Normalise n'importe quelle valeur : certaines sources (APEC) renvoient des
    codes numeriques la ou on attend une chaine."""
    normalized = unicodedata.normalize("NFKD", str(text if text is not None else "").lower())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _contains(text: str, keyword: str) -> bool:
    kw = _normalize(str(keyword))
    if not kw:
        return False
    normalized_text = _normalize(text)
    if len(kw) <= 3 and kw.replace(" ", "").isalnum():
        token_text = " " + re.sub(r"[^a-z0-9]+", " ", normalized_text) + " "
        return f" {kw} " in token_text
    return kw in normalized_text


def _detect_sector(job: Dict, criteria: Dict) -> Tuple[str, int]:
    text = _normalize(f"{job.get('title','')} {job.get('description','')} {job.get('company','')}")
    sectors = criteria.get("sectors", {})
    for sector_name, sector_cfg in sectors.items():
        for kw in sector_cfg.get("keywords", []):
            if _contains(text, kw):
                return sector_name, int(sector_cfg.get("score_weight", 0))
    return "unknown", 0


def _score_position(title: str, criteria: Dict, sector: str) -> int:
    title_l = _normalize(title)
    score = 0
    for position in criteria.get("target_positions", []):
        keywords = [kw for kw in position.get("keywords", [])]
        if any(_contains(title_l, kw) for kw in keywords):
            # Respect sector restriction if present
            restriction = position.get("sector_restriction")
            if restriction and sector.lower() not in [s.lower() for s in restriction]:
                continue
            score = max(score, int(position.get("score_weight", 0)))
    return score


def _score_contract(job: Dict, criteria: Dict) -> int:
    contract = _normalize(job.get("contract_type") or "")
    text = _normalize(f"{contract} {job.get('description','')}")
    best = 0
    for cfg in criteria.get("contracts", {}).get("accepted", []):
        ctype = _normalize(cfg.get("type", ""))
        if ctype and (ctype in contract or ctype in text):
            best = max(best, int(cfg.get("score_weight", 0)))
    return best


def _score_location(job: Dict, criteria: Dict) -> int:
    location_cfg = criteria.get("location", {})
    weights = location_cfg.get("score_weights", {})
    text = _normalize(f"{job.get('location','')} {job.get('description','')}")

    # Paris reste prioritaire, mais toute l'Île-de-France est compatible.
    if "paris" in text or any(code in text for code in [
        "75001", "75002", "75003", "75004", "75005", "75006", "75007", "75008", "75009", "75010",
        "75011", "75012", "75013", "75014", "75015", "75016", "75017", "75018", "75019", "75020",
    ]):
        return int(weights.get("paris", 10))

    idf_terms = [
        "ile-de-france", "idf",
        "77", "78", "91", "92", "93", "94", "95",
        "seine-et-marne", "yvelines", "essonne", "hauts-de-seine",
        "seine-saint-denis", "val-de-marne", "val-d'oise", "val d'oise",
        "boulogne-billancourt", "nanterre", "courbevoie", "la defense", "levallois-perret",
        "issy-les-moulineaux", "saint-cloud", "versailles", "saint-germain-en-laye",
        "velizy", "velizy-villacoublay", "guyancourt", "massy", "evry", "saclay", "orsay",
        "cergy", "argenteuil", "roissy", "pontoise",
        "pantin", "montreuil", "bagnolet", "les lilas", "romainville", "saint-denis", "bobigny",
        "noisy-le-grand", "creteil", "ivry", "vincennes", "fontenay", "vitry", "maisons-alfort",
        "melun", "meaux", "torcy", "chessy",
    ]
    if any(term in text for term in idf_terms):
        return int(weights.get("idf", 8))

    if "remote" in text or "teletravail" in text:
        return int(weights.get("remote", 0))
    if "hybrid" in text or "hybride" in text:
        return int(weights.get("hybrid", 0))
    return 0


def _combined_text(job: Dict) -> str:
    return _normalize(
        " ".join(
            str(job.get(field, ""))
            for field in ("title", "description", "requirements", "company", "location")
        )
    )


def _score_skill_bonus(job: Dict, criteria: Dict) -> int:
    cfg = criteria.get("skills_matching", {})
    if not cfg.get("enabled", False):
        return 0
    text = _combined_text(job)
    total = 0
    for group_name in ("hard_bonus", "soft_bonus"):
        for skill_cfg in cfg.get(group_name, []):
            variants = skill_cfg.get("variants", [])
            if any(_contains(text, str(variant)) for variant in variants):
                total += int(skill_cfg.get("points", 0))
    return total


def _score_experience_penalty(job: Dict, criteria: Dict) -> int:
    """Penalize offers that require more experience than the user has."""
    text = _combined_text(job)
    tech_xp = int(criteria.get("user_profile", {}).get("tech_experience_years", 2))
    total = 0

    # Détecter les mentions d'XP élevée
    for keyword, years in [("10 ans", 10), ("dix ans", 10), ("8 ans", 8),
                            ("5 ans", 5), ("cinq ans", 5), ("7 ans", 7),
                            ("minimum 5", 5), ("minimum 3", 3)]:
        if _contains(text, keyword) and years > tech_xp + 1:
            total += -12 * (years - tech_xp)

    # "Senior", "expert", "confirmé" → pénalité modérée
    senior_keywords = ["senior", "expert", "confirme", "confirmé", "tech lead", "lead developer"]
    for keyword in senior_keywords:
        if _contains(text, keyword) and tech_xp < 4:
            total += -15
            break  # une seule pénalité "senior" max

    # Bonus pour junior/débutant
    for keyword in ["junior", "debutant", "débutant", "premiere experience", "première expérience"]:
        if _contains(text, keyword):
            total += 10

    # Bonus pour publics spécifiques (insertion, handicap)
    for keyword in ["handicap", "insertion", "public eloigne", "public éloigné", "reconversion"]:
        if _contains(text, keyword):
            total += 8

    return max(-80, min(20, total))


def _score_penalties(job: Dict, criteria: Dict) -> int:
    text = _combined_text(job)
    total = 0

    for penalty in criteria.get("red_flags", {}).get("soft_penalty_keywords", []):
        keyword = penalty.get("keyword")
        if keyword and _contains(text, str(keyword)):
            total += int(penalty.get("points", 0))

    for penalty in criteria.get("skills_matching", {}).get("mismatch_penalties", []):
        if any(_contains(text, str(keyword)) for keyword in penalty.get("keywords", [])):
            total += int(penalty.get("points", 0))

    return total


def calculate_score(job: Dict, criteria: Dict) -> int:
    sector, sector_score = _detect_sector(job, criteria)
    job["sector"] = sector

    score = 0
    score += _score_position(job.get("title", ""), criteria, sector)
    score += sector_score
    score += _score_contract(job, criteria)
    score += _score_location(job, criteria)
    score += _score_skill_bonus(job, criteria)
    score += _score_penalties(job, criteria)
    score += _score_experience_penalty(job, criteria)

    # Bonus récence : +5 si publié depuis < 7 jours
    published = job.get("published_at", "")
    if published:
        try:
            pub_date = datetime.fromisoformat(published.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - pub_date).days
            if age_days <= 3:
                score += 5
            elif age_days <= 7:
                score += 3
            elif age_days <= 14:
                score += 1
        except (ValueError, TypeError):
            pass

    if job.get("salary"):
        score += int(criteria.get("scoring", {}).get("bonus_points", {}).get("salary_mentioned", 0))

    return max(0, min(score, 100))
