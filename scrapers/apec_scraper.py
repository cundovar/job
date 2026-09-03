"""
APEC scraper using their JSON API.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, List

import requests

from utils.rate_limiter import rate_limit
from .base_scraper import BaseScraper, balanced_keyword_limits


class APECScraper(BaseScraper):
    SEARCH_URL = "https://www.apec.fr/cms/webservices/rechercheOffre"

    def __init__(self) -> None:
        self.max_jobs = int(os.getenv("MAX_JOBS_PER_SITE", "50"))
        self.max_keywords = int(os.getenv("MAX_KEYWORDS_PER_SOURCE", "10"))
        self.timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
        raw_location_ids = os.getenv("APEC_LOCATION_IDS", "711")
        self.location_ids = [
            int(value.strip())
            for value in raw_location_ids.split(",")
            if value.strip()
        ]
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    @rate_limit(delay_seconds=int(os.getenv("SCRAPING_DELAY_SECONDS", "3")))
    def _search(self, keyword: str) -> List[Dict]:
        payload = {
            "motsCles": keyword,
            "lieux": self.location_ids,
            "sorts": [{"type": "DATE", "direction": "DESCENDING"}],
            "pagination": {"range": 50, "startIndex": 0},
        }
        resp = self.session.post(
            self.SEARCH_URL,
            json=payload,
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        return resp.json().get("resultats", [])

    # Codes releves sur 206 offres APEC (5 mots-cles, 03/09/2026).
    CONTRACT_TYPES = {
        101888: "CDI",
        101887: "CDD",
        597137: "Alternance",
    }

    def _contract_label(self, raw: Dict) -> str:
        """L'API APEC renvoie typeContrat comme code numerique, pas comme libelle."""
        value = raw.get("typeContrat") or raw.get("contract") or ""
        try:
            return self.CONTRACT_TYPES.get(int(value), str(value))
        except (TypeError, ValueError):
            return str(value)

    def _parse_job(self, raw: Dict) -> Dict:
        return {
            "title": raw.get("intitule", "") or raw.get("title", ""),
            "company": raw.get("nomCommercial", "") or raw.get("nomCompagnie", "") or raw.get("company", "") or raw.get("entreprise", ""),
            "location": raw.get("lieuTexte", "") or raw.get("lieuTravail", "") or raw.get("location", "") or raw.get("localisation", ""),
            "contract_type": self._contract_label(raw),
            "salary": raw.get("salaireTexte", "") or raw.get("salaire", "") or raw.get("salary", ""),
            "description": raw.get("texteOffre", "") or raw.get("texteHtml", "") or raw.get("description", "") or raw.get("texte", ""),
            "url": f"https://www.apec.fr/candidat/recherche-emploi.html/emploi/detail-offre/{raw.get('numeroOffre', '')}"
                   if raw.get("numeroOffre") else raw.get("url", ""),
            "source": "apec",
            "published_at": raw.get("datePublication", ""),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }

    def scrape(self, keywords: List[str]) -> List[Dict]:
        jobs: List[Dict] = []
        seen_urls = set()

        allocations = balanced_keyword_limits(
            keywords,
            self.max_jobs,
            self.max_keywords,
        )
        for keyword, keyword_limit in allocations:
            added_for_keyword = 0
            results = self._search(keyword)
            for raw in results:
                job = self._parse_job(raw)
                if job["title"] and job["url"] and job["url"] not in seen_urls:
                    seen_urls.add(job["url"])
                    jobs.append(job)
                    added_for_keyword += 1
                if len(jobs) >= self.max_jobs or added_for_keyword >= keyword_limit:
                    break
        return jobs
