"""
Abstract base class for all scrapers.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List


class BaseScraper(ABC):
    @abstractmethod
    def scrape(self, keywords: List[str]) -> List[Dict]:
        raise NotImplementedError
