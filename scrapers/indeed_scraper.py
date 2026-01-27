"""
Indeed.fr scraper (basic HTML parsing).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, List

import requests
from bs4 import BeautifulSoup

from utils.rate_limiter import rate_limit
from .base_scraper import BaseScraper


class IndeedScraper(BaseScraper):
    BASE_URL = "https://fr.indeed.com/jobs"

    def __init__(self) -> None:
        self.max_jobs = int(os.getenv("MAX_JOBS_PER_SITE", "50"))
        self.timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))

    @rate_limit(delay_seconds=int(os.getenv("SCRAPING_DELAY_SECONDS", "2")))
    def _get(self, params: Dict[str, str]) -> str:
        resp = requests.get(
            self.BASE_URL,
            params=params,
            timeout=self.timeout_seconds,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            },
        )
        resp.raise_for_status()
        return resp.text

    def _parse_job_card(self, card) -> Dict:
        title_el = card.select_one("h2.jobTitle span")
        company_el = card.select_one("span.companyName")
        location_el = card.select_one("div.companyLocation")
        salary_el = card.select_one("div.metadata.salary-snippet-container")
        summary_el = card.select_one("div.job-snippet")
        link_el = card.select_one("a")

        title = title_el.get_text(strip=True) if title_el else ""
        company = company_el.get_text(strip=True) if company_el else ""
        location = location_el.get_text(strip=True) if location_el else ""
        salary = salary_el.get_text(" ", strip=True) if salary_el else None
        description = summary_el.get_text(" ", strip=True) if summary_el else ""

        url = None
        if link_el and link_el.get("href"):
            href = link_el["href"]
            url = href if href.startswith("http") else f"https://fr.indeed.com{href}"

        return {
            "title": title,
            "company": company,
            "location": location,
            "contract_type": None,
            "salary": salary,
            "description": description,
            "url": url,
            "source": "indeed",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }

    def scrape(self, keywords: List[str]) -> List[Dict]:
        jobs: List[Dict] = []
        for keyword in keywords:
            params = {"q": keyword, "l": "Île-de-France"}
            html = self._get(params=params)
            soup = BeautifulSoup(html, "lxml")
            cards = soup.select("div.job_seen_beacon")
            for card in cards:
                job = self._parse_job_card(card)
                if job["title"]:
                    jobs.append(job)
                if len(jobs) >= self.max_jobs:
                    return jobs
        return jobs
