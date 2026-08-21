"""
Jooble API scraper.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, List

import requests

from .base_scraper import BaseScraper


class JoobleScraper(BaseScraper):
    API_ROOT = "https://jooble.org/api"

    def __init__(
        self,
        api_key: str | None = None,
        country: str = "fr",
        location: str = "Paris",
        max_jobs: int = 50,
        timeout_seconds: int = 30,
    ) -> None:
        self.api_key = api_key or os.getenv("JOOBLE_API_KEY")
        self.country = country
        self.location = location
        self.max_jobs = max_jobs
        self.timeout_seconds = timeout_seconds

    def _search(self, keyword: str) -> Dict:
        if not self.api_key:
            raise ValueError("Missing JOOBLE_API_KEY")
        response = requests.post(
            f"{self.API_ROOT}/{self.api_key}",
            json={"keywords": keyword, "location": self.location, "page": 1},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}

    def _parse_job(self, raw: Dict) -> Dict:
        return {
            "title": raw.get("title", ""),
            "company": raw.get("company", ""),
            "location": raw.get("location", ""),
            "contract_type": raw.get("type", ""),
            "salary": raw.get("salary"),
            "description": raw.get("snippet", "") or raw.get("description", ""),
            "url": raw.get("link", ""),
            "source": "jooble",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }

    def scrape(self, keywords: List[str]) -> List[Dict]:
        jobs: List[Dict] = []
        seen_urls = set()
        for keyword in keywords:
            data = self._search(keyword)
            for raw in data.get("jobs", []):
                job = self._parse_job(raw)
                url = job.get("url")
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)
                if job.get("title"):
                    jobs.append(job)
                if len(jobs) >= self.max_jobs:
                    return jobs
        return jobs
