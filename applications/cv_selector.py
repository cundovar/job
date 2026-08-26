"""
Select the best CV variant for a job offer.

Variants come from data/cv_master_profile.json. There is no PDF path: the CV
itself is generated on demand by cv_generator from the master profile, so a
recommendation names a starting variant, not a file.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Sequence

from .cv_variants import CVVariant, default_priority, load_cv_variants


@dataclass(frozen=True)
class CVRecommendation:
    cv_id: str
    cv_name: str
    score: int
    matched_keywords: List[str]
    reason: str


def _normalize(value: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )
    lowered = without_accents.lower()
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


def _job_text(job: Dict) -> str:
    parts = [
        job.get("title", ""),
        job.get("description", ""),
        job.get("requirements", ""),
        job.get("company", ""),
        job.get("sector", ""),
    ]
    return _normalize(" ".join(str(part) for part in parts if part))


def _variant_score(variant: CVVariant, text: str) -> tuple[int, List[str]]:
    """Match tags on word boundaries: 'ia' must not match inside 'social'."""
    matched = []
    for tag in variant.tags:
        normalized = _normalize(tag)
        if normalized and re.search(rf"\b{re.escape(normalized)}\b", text):
            matched.append(tag)
    return len(matched), matched


def recommend_cv(
    job: Dict,
    variants: Sequence[CVVariant] | None = None,
) -> CVRecommendation:
    cv_variants = list(variants) if variants is not None else load_cv_variants()
    if not cv_variants:
        raise ValueError("Aucune variante de CV dans cv_master_profile.json")

    priority = default_priority() if variants is None else []

    def tie_break(variant_id: str) -> int:
        """Lower is better: honour positioning.default_priority on equal scores."""
        try:
            return priority.index(variant_id)
        except ValueError:
            return len(priority) + 1

    text = _job_text(job)
    ranked = []
    for index, variant in enumerate(cv_variants):
        score, matched = _variant_score(variant, text)
        ranked.append((score, -tie_break(variant.id), -index, variant, matched))

    score, _, _, best, matched_keywords = max(ranked, key=lambda item: item[:3])

    if matched_keywords:
        reason = "Correspondance avec: " + ", ".join(matched_keywords[:5])
    else:
        reason = "Aucun mot-cle fort detecte; variante par defaut selon positioning.default_priority."

    return CVRecommendation(
        cv_id=best.id,
        cv_name=best.name,
        score=score,
        matched_keywords=matched_keywords,
        reason=reason,
    )
