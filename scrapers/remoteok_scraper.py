"""
Remote OK API scraper.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

import requests

from .base_scraper import BaseScraper


class RemoteOKScraper(BaseScraper):
    API_URL = "https://remoteok.com/api"

    def __init__(self, max_jobs: int = 50, timeout_seconds: int = 30) -> None:
        self.max_jobs = max_jobs
        self.timeout_seconds = timeout_seconds

    def _fetch(self) -> List[Dict]:
        response = requests.get(
            self.API_URL,
            headers={"User-Agent": "job-search-automation/1.0"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    def _matches_keywords(self, raw: Dict, keywords: List[str]) -> bool:
        if not keywords:
            return True
        text = " ".join(
            [
                str(raw.get("position", "")),
                str(raw.get("description", "")),
                " ".join(str(tag) for tag in raw.get("tags", []) if tag),
            ]
        ).lower()
        return any(keyword.lower() in text for keyword in keywords)

    def _parse_job(self, raw: Dict) -> Dict:
        salary_min = raw.get("salary_min") or 0
        salary_max = raw.get("salary_max") or 0
        salary = None
        if salary_min or salary_max:
            salary = f"{salary_min} - {salary_max}".strip()

        return {
            "title": raw.get("position", ""),
            "company": raw.get("company", ""),
            "location": raw.get("location", "") or "Remote",
            "contract_type": "Remote",
            "salary": salary,
            "description": raw.get("description", ""),
            "url": raw.get("url") or raw.get("apply_url", ""),
            "source": "remoteok",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }

    def scrape(self, keywords: List[str]) -> List[Dict]:
        jobs: List[Dict] = []
        seen_urls = set()
        for raw in self._fetch():
            if "legal" in raw:
                continue
            if not self._matches_keywords(raw, keywords):
                continue
            job = self._parse_job(raw)
            url = job.get("url")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            if job.get("title"):
                jobs.append(job)
            if len(jobs) >= self.max_jobs:
                break
        return jobs
