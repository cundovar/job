"""
LesJeudis.com scraper — site d'emploi IT/Tech, ~5000 offres.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Dict, List

import requests
from bs4 import BeautifulSoup

from utils.rate_limiter import rate_limit
from .base_scraper import BaseScraper


class LesJeudisScraper(BaseScraper):
    BASE_URL = "https://lesjeudis.com/jobs"

    def __init__(self) -> None:
        self.max_jobs = int(os.getenv("MAX_JOBS_PER_SITE", "50"))
        self.timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
        })

    @rate_limit(delay_seconds=int(os.getenv("SCRAPING_DELAY_SECONDS", "2")))
    def _search(self, keyword: str) -> str:
        resp = self.session.get(
            self.BASE_URL,
            params={"search": keyword},
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        return resp.text

    def _parse_card(self, text: str, link_text: str, href: str) -> Dict:
        clean = text.replace("Aucun logo disponible", "").strip()

        # Location
        loc_match = re.search(r'location\s+(.+?)\s+remote', clean)
        location = loc_match.group(1).strip() if loc_match else ""

        # Remote
        remote_match = re.search(r'remote\s+(.+?)\s+Publié', clean)
        remote_raw = remote_match.group(1).strip() if remote_match else ""
        remote = "" if "pas de" in remote_raw.lower() else remote_raw

        # Company: text between title and "location"
        title_pos = clean.find(link_text)
        company = ""
        if title_pos >= 0:
            after_title = clean[title_pos + len(link_text):]
            loc_pos = after_title.find("location")
            if loc_pos >= 0:
                company = after_title[:loc_pos].strip()

        # Description: try to get a snippet from the detail page
        # We skip this to keep things fast — scoring will use title+company+location

        url = href if href.startswith("http") else f"https://lesjeudis.com{href}"

        return {
            "title": link_text,
            "company": company,
            "location": location,
            "contract_type": None,
            "salary": None,
            "description": f"{company} — {location}",
            "url": url,
            "source": "lesjeudis",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }

    def scrape(self, keywords: List[str]) -> List[Dict]:
        jobs: List[Dict] = []

        for keyword in keywords:
            if len(jobs) >= self.max_jobs:
                break

            try:
                html = self._search(keyword)
            except Exception:
                continue

            soup = BeautifulSoup(html, "lxml")

            # Find the container holding all job cards
            first_link = soup.find("a", href=lambda h: h and "/fr/job/" in h)
            if not first_link:
                continue

            container = first_link
            for _ in range(6):
                container = container.parent
                if len(container.find_all("a", href=lambda h: h and "/fr/job/" in h)) >= 3:
                    break

            for child in container.find_all(recursive=False):
                if len(jobs) >= self.max_jobs:
                    return jobs

                link = child.find("a", href=lambda h: h and "/fr/job/" in h)
                if not link:
                    continue

                text = child.get_text(" ", strip=True)
                job = self._parse_card(text, link.get_text(strip=True), link.get("href", ""))
                if job["title"]:
                    jobs.append(job)

        return jobs
