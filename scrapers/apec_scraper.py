"""
APEC scraper using their JSON API.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, List

import requests

from utils.rate_limiter import rate_limit
from .base_scraper import BaseScraper


class APECScraper(BaseScraper):
    SEARCH_URL = "https://www.apec.fr/cms/webservices/rechercheOffre"

    def __init__(self) -> None:
        self.max_jobs = int(os.getenv("MAX_JOBS_PER_SITE", "50"))
        self.timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
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
            "lieux": [{"libelle": "Île-de-France", "typeZone": 1}],
            "sortsAndFilters": {
                "sorts": [{"type": "DATE", "direction": "DESCENDING"}],
            },
            "pagination": {"range": 50, "startIndex": 0},
        }
        try:
            resp = self.session.post(
                self.SEARCH_URL,
                json=payload,
                timeout=self.timeout_seconds
            )
            resp.raise_for_status()
            return resp.json().get("resultats", [])
        except Exception:
            # Fallback: essayer l'ancien format
            return self._search_fallback(keyword)

    def _search_fallback(self, keyword: str) -> List[Dict]:
        """Fallback using HTML scraping if API fails."""
        url = f"https://www.apec.fr/candidat/recherche-emploi.html/emploi?motsCles={keyword}"
        try:
            resp = self.session.get(url, timeout=self.timeout_seconds)
            resp.raise_for_status()
            # Chercher les données JSON intégrées dans la page
            import re
            import json
            match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', resp.text)
            if match:
                data = json.loads(match.group(1))
                return data.get("searchResults", {}).get("results", [])
        except Exception:
            pass
        return []

    def _parse_job(self, raw: Dict) -> Dict:
        return {
            "title": raw.get("intitule", "") or raw.get("title", ""),
            "company": raw.get("nomCompagnie", "") or raw.get("company", "") or raw.get("entreprise", ""),
            "location": raw.get("lieuTravail", "") or raw.get("location", "") or raw.get("localisation", ""),
            "contract_type": raw.get("typeContrat", "") or raw.get("contract", ""),
            "salary": raw.get("salaire", "") or raw.get("salary", ""),
            "description": raw.get("texteHtml", "") or raw.get("description", "") or raw.get("texte", ""),
            "url": f"https://www.apec.fr/candidat/recherche-emploi.html/emploi/detail-offre/{raw.get('numeroOffre', '')}"
                   if raw.get("numeroOffre") else raw.get("url", ""),
            "source": "apec",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }

    def scrape(self, keywords: List[str]) -> List[Dict]:
        jobs: List[Dict] = []
        seen_urls = set()

        for keyword in keywords[:5]:  # Limiter à 5 keywords pour éviter trop de requêtes
            results = self._search(keyword)
            for raw in results:
                job = self._parse_job(raw)
                if job["title"] and job["url"] and job["url"] not in seen_urls:
                    seen_urls.add(job["url"])
                    jobs.append(job)
                if len(jobs) >= self.max_jobs:
                    return jobs
        return jobs
