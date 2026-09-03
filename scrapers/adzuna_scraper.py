"""
Adzuna API scraper.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

from utils.rate_limiter import rate_limit
from .base_scraper import BaseScraper, balanced_keyword_limits


class AdzunaScraper(BaseScraper):
    API_ROOT = "https://api.adzuna.com/v1/api/jobs"

    def __init__(self) -> None:
        self.app_id = os.getenv("ADZUNA_APP_ID")
        self.app_key = os.getenv("ADZUNA_APP_KEY")
        self.country = os.getenv("ADZUNA_COUNTRY", "fr")
        self.location = os.getenv("ADZUNA_LOCATION", "Île-de-France")
        self.max_jobs = int(os.getenv("MAX_JOBS_PER_SITE", "50"))
        self.max_keywords = int(os.getenv("MAX_KEYWORDS_PER_SOURCE", "10"))
        self.results_per_page = int(os.getenv("ADZUNA_RESULTS_PER_PAGE", "20"))
        self.timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
        self.max_retries = max(1, int(os.getenv("ADZUNA_MAX_RETRIES", "3")))
        self.retry_backoff_seconds = max(
            0.0, float(os.getenv("ADZUNA_RETRY_BACKOFF_SECONDS", "1"))
        )

    @rate_limit(delay_seconds=int(os.getenv("SCRAPING_DELAY_SECONDS", "2")))
    def _search(self, keyword: str, page: int) -> Dict:
        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "what": keyword,
            "where": self.location,
            "results_per_page": self.results_per_page,
            "content-type": "application/json",
        }
        url = f"{self.API_ROOT}/{self.country}/search/{page}"
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.get(url, params=params, timeout=self.timeout_seconds)
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise RuntimeError(
                        f"Adzuna API inaccessible apres {self.max_retries} tentatives"
                    ) from exc
            else:
                if resp.status_code < 400:
                    return resp.json()
                retryable = resp.status_code == 429 or resp.status_code >= 500
                if not retryable or attempt == self.max_retries:
                    # Ne pas appeler raise_for_status(): son message contient
                    # l'URL complete et donc app_id/app_key dans les journaux.
                    raise RuntimeError(f"Adzuna API HTTP {resp.status_code}")

            time.sleep(self.retry_backoff_seconds * attempt)

        raise RuntimeError("Adzuna API inaccessible")

    def _parse_job(self, raw: Dict) -> Dict:
        company = raw.get("company", {}) or {}
        location = raw.get("location", {}) or {}
        salary_min = raw.get("salary_min")
        salary_max = raw.get("salary_max")
        salary = None
        if salary_min or salary_max:
            if salary_min and salary_max:
                salary = f"{int(salary_min)} - {int(salary_max)}"
            elif salary_min:
                salary = f"à partir de {int(salary_min)}"
            else:
                salary = f"jusqu'à {int(salary_max)}"

        return {
            "title": raw.get("title", ""),
            "company": company.get("display_name", ""),
            "location": location.get("display_name", ""),
            "contract_type": raw.get("contract_time", "") or raw.get("contract_type", ""),
            "salary": salary,
            "description": raw.get("description", ""),
            "url": raw.get("redirect_url", ""),
            "source": "adzuna",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }

    def scrape(self, keywords: List[str]) -> List[Dict]:
        if not self.app_id or not self.app_key:
            raise ValueError("Missing ADZUNA_APP_ID or ADZUNA_APP_KEY")

        jobs: List[Dict] = []
        seen_urls = set()

        allocations = balanced_keyword_limits(
            keywords,
            self.max_jobs,
            self.max_keywords,
        )
        for keyword, keyword_limit in allocations:
            page = 1
            added_for_keyword = 0
            while len(jobs) < self.max_jobs and added_for_keyword < keyword_limit:
                data = self._search(keyword, page)
                results = data.get("results", [])
                if not results:
                    break

                for raw in results:
                    url = raw.get("redirect_url")
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)
                    job = self._parse_job(raw)
                    if job["title"]:
                        jobs.append(job)
                        added_for_keyword += 1
                    if len(jobs) >= self.max_jobs or added_for_keyword >= keyword_limit:
                        break

                page += 1

        return jobs
