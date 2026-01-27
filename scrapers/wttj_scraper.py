"""
Welcome to the Jungle scraper via GraphQL API.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Dict, List

import requests

from utils.rate_limiter import rate_limit
from .base_scraper import BaseScraper


class WTTJScraper(BaseScraper):
    API_URL = "https://www.welcometothejungle.com/api/graphql"

    def __init__(self) -> None:
        self.max_jobs = int(os.getenv("MAX_JOBS_PER_SITE", "50"))
        self.timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))

    @rate_limit(delay_seconds=int(os.getenv("SCRAPING_DELAY_SECONDS", "2")))
    def _post(self, payload: Dict) -> Dict:
        resp = requests.post(
            self.API_URL,
            json=payload,
            timeout=self.timeout_seconds,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        return resp.json()

    def _build_query(self) -> str:
        return """
        query SearchJobs($query: String!, $page: Int!) {
          jobs(query: $query, page: $page) {
            items {
              id
              name
              company {
                name
              }
              contractType
              location {
                name
              }
              description
              publishedAt
              slug
            }
          }
        }
        """

    def scrape(self, keywords: List[str]) -> List[Dict]:
        jobs: List[Dict] = []
        query = self._build_query()
        for keyword in keywords:
            page = 1
            while len(jobs) < self.max_jobs:
                payload = {"query": query, "variables": {"query": keyword, "page": page}}
                data = self._post(payload)
                items = (
                    data.get("data", {})
                    .get("jobs", {})
                    .get("items", [])
                )
                if not items:
                    break
                for item in items:
                    job = {
                        "title": item.get("name") or "",
                        "company": (item.get("company") or {}).get("name", ""),
                        "location": (item.get("location") or {}).get("name", ""),
                        "contract_type": item.get("contractType"),
                        "salary": None,
                        "description": item.get("description") or "",
                        "url": f"https://www.welcometothejungle.com/fr/jobs/{item.get('slug')}"
                        if item.get("slug")
                        else None,
                        "source": "wttj",
                        "scraped_at": datetime.now(timezone.utc).isoformat(),
                    }
                    if job["title"]:
                        jobs.append(job)
                    if len(jobs) >= self.max_jobs:
                        return jobs
                page += 1
        return jobs
