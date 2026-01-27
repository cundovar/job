"""
Emploi-asso.org scraper (basic HTML parsing).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from utils.rate_limiter import rate_limit
from .base_scraper import BaseScraper


class EmploiAssoScraper(BaseScraper):
    BASE_URL = "https://www.emploi-asso.org/recherche"

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

    def _first_text(self, parent, selectors: List[str]) -> str:
        for sel in selectors:
            el = parent.select_one(sel)
            if el:
                return el.get_text(" ", strip=True)
        return ""

    def _first_link(self, parent, selectors: List[str]) -> Optional[str]:
        for sel in selectors:
            el = parent.select_one(sel)
            if el and el.get("href"):
                href = el["href"]
                return href if href.startswith("http") else f"https://www.emploi-asso.org{href}"
        return None

    def _parse_card(self, card) -> Dict:
        title = self._first_text(card, ["h2 a", "h3 a", "h2", "h3", "a.title", "a"])
        company = self._first_text(card, [".company", ".employer", ".org", ".organization"])
        location = self._first_text(card, [".location", ".city", ".place"])
        contract = self._first_text(card, [".contract", ".type", ".contrat"])
        description = self._first_text(card, [".description", ".excerpt", ".summary", "p"])
        url = self._first_link(card, ["h2 a", "h3 a", "a.title", "a"])

        return {
            "title": title,
            "company": company,
            "location": location,
            "contract_type": contract or None,
            "salary": None,
            "description": description,
            "url": url,
            "source": "emploi_asso",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }

    def scrape(self, keywords: List[str]) -> List[Dict]:
        jobs: List[Dict] = []
        for keyword in keywords:
            params = {"q": keyword, "location": "Île-de-France"}
            html = self._get(params=params)
            soup = BeautifulSoup(html, "lxml")

            cards = soup.select("article, .job, .job-item, .result, .search-result")
            for card in cards:
                job = self._parse_card(card)
                if job["title"]:
                    jobs.append(job)
                if len(jobs) >= self.max_jobs:
                    return jobs
        return jobs
