"""emploi-ess.fr — portail de l'ESS, spécialisé économie sociale et solidaire."""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Dict, List

import requests
from bs4 import BeautifulSoup

from utils.rate_limiter import rate_limit
from .base_scraper import BaseScraper, balanced_keyword_limits


class EmploiESSScraper(BaseScraper):
    BASE_URL = "https://www.emploi-ess.fr/offres-d-emploi"

    def __init__(self) -> None:
        self.max_jobs = int(os.getenv("MAX_JOBS_PER_SITE", "50"))
        self.max_keywords = int(os.getenv("MAX_KEYWORDS_PER_SOURCE", "10"))
        self.timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "fr-FR,fr;q=0.9",
        })

    @rate_limit(delay_seconds=int(os.getenv("SCRAPING_DELAY_SECONDS", "2")))
    def _search(self, keyword: str) -> str:
        resp = self.session.get(
            self.BASE_URL,
            params={"m": keyword},
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        return resp.text

    def scrape(self, keywords: List[str]) -> List[Dict]:
        jobs: List[Dict] = []
        seen = set()

        allocations = balanced_keyword_limits(
            keywords,
            self.max_jobs,
            self.max_keywords,
        )
        request_errors = []
        successful_requests = 0
        for keyword, keyword_limit in allocations:
            if len(jobs) >= self.max_jobs:
                break
            try:
                html = self._search(keyword)
                successful_requests += 1
            except Exception as exc:
                request_errors.append(exc)
                continue

            soup = BeautifulSoup(html, "lxml")
            added_for_keyword = 0

            for card in soup.select(".bloc-offre"):
                title_el = card.select_one(".offre-titre a")
                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                link = title_el
                url = link.get("href", "") if link else ""
                if url and not url.startswith("http"):
                    url = f"https://www.emploi-ess.fr/{url.lstrip('/')}"

                dedup_key = url or title[:60]
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                location_el = card.select_one(".offre-localisation span")
                location = location_el.get_text(" ", strip=True) if location_el else ""
                description_el = card.select_one(".offre-descriptif")
                description = (
                    description_el.get_text(" ", strip=True)
                    if description_el
                    else card.get_text(" ", strip=True)
                )
                contract_match = re.search(
                    r"\b(CDI|CDD|freelance|stage|alternance)\b",
                    description,
                    flags=re.IGNORECASE,
                )
                date_el = card.select_one(".offre-date")
                published_at = ""
                if date_el:
                    try:
                        published_at = datetime.strptime(
                            date_el.get_text(strip=True),
                            "%d/%m/%Y",
                        ).date().isoformat()
                    except ValueError:
                        published_at = ""

                jobs.append({
                    "title": title,
                    "company": "ESS",
                    "location": location or "Île-de-France",
                    "contract_type": contract_match.group(1).upper() if contract_match else None,
                    "salary": None,
                    "description": description[:800],
                    "url": url,
                    "source": "emploi_ess",
                    "published_at": published_at,
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                })
                added_for_keyword += 1
                if len(jobs) >= self.max_jobs or added_for_keyword >= keyword_limit:
                    break

        if allocations and successful_requests == 0 and request_errors:
            raise RuntimeError(
                f"Emploi-ESS inaccessible pour {len(request_errors)} requêtes"
            ) from request_errors[-1]

        return jobs
