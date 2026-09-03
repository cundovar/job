"""
Abstract base class for all scrapers.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List


def balanced_keyword_limits(
    keywords: List[str],
    max_jobs: int,
    max_keywords: int = 10,
) -> List[tuple[str, int]]:
    """Allocate a source's capacity across distinct, ordered keywords."""
    unique_keywords: List[str] = []
    seen = set()
    for keyword in keywords:
        cleaned = str(keyword).strip()
        normalized = cleaned.casefold()
        if cleaned and normalized not in seen:
            seen.add(normalized)
            unique_keywords.append(cleaned)

    selected = unique_keywords[: max(0, max_keywords)]
    if not selected or max_jobs <= 0:
        return []
    selected = selected[:max_jobs]
    base, remainder = divmod(max_jobs, len(selected))
    return [
        (keyword, base + (1 if index < remainder else 0))
        for index, keyword in enumerate(selected)
    ]


class BaseScraper(ABC):
    @abstractmethod
    def scrape(self, keywords: List[str]) -> List[Dict]:
        raise NotImplementedError
