"""
Select the best existing CV for a job offer.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

from .cv_profiles import CVProfile, load_cv_profiles


@dataclass(frozen=True)
class CVRecommendation:
    cv_id: str
    cv_name: str
    cv_path: str
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
    return re.sub(r"\s+", " ", lowered).strip()


def _job_text(job: Dict) -> str:
    parts = [
        job.get("title", ""),
        job.get("description", ""),
        job.get("requirements", ""),
        job.get("company", ""),
        job.get("sector", ""),
    ]
    return _normalize(" ".join(str(part) for part in parts if part))


def _profile_score(profile: CVProfile, text: str) -> tuple[int, List[str]]:
    matched = []
    for keyword in profile.best_for:
        normalized_keyword = _normalize(keyword)
        if normalized_keyword and normalized_keyword in text:
            matched.append(keyword)

    return len(matched), matched


def _first_existing_path(profile: CVProfile) -> str:
    for path in [profile.path, *profile.alternatives]:
        if Path(path).exists():
            return path
    return profile.path


def recommend_cv(
    job: Dict,
    profiles: Sequence[CVProfile] | None = None,
) -> CVRecommendation:
    cv_profiles = list(profiles) if profiles is not None else load_cv_profiles()
    if not cv_profiles:
        raise ValueError("No CV profiles configured")

    text = _job_text(job)
    ranked = []
    for index, profile in enumerate(cv_profiles):
        score, matched_keywords = _profile_score(profile, text)
        ranked.append((score, -index, profile, matched_keywords))

    score, _, best_profile, matched_keywords = max(ranked, key=lambda item: (item[0], item[1]))
    cv_path = _first_existing_path(best_profile)
    if matched_keywords:
        reason = "Correspondance avec: " + ", ".join(matched_keywords[:5])
    else:
        reason = "Aucun mot-cle fort detecte; CV par defaut le plus general dans la configuration."

    return CVRecommendation(
        cv_id=best_profile.id,
        cv_name=best_profile.name,
        cv_path=cv_path,
        score=score,
        matched_keywords=matched_keywords,
        reason=reason,
    )
