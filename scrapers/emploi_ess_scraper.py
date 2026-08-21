"""emploi-ess.fr — portail de l'ESS, spécialisé économie sociale et solidaire."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, List

import requests
from bs4 import BeautifulSoup

from utils.rate_limiter import rate_limit
from .base_scraper import BaseScraper


class EmploiESSScraper(BaseScraper):
    BASE_URL = "https://www.emploi-ess.fr/offres-d-emploi"

    def __init__(self) -> None:
        self.max_jobs = int(os.getenv("MAX_JOBS_PER_SITE", "50"))
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
            params={"search": keyword},
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        return resp.text

    def scrape(self, keywords: List[str]) -> List[Dict]:
        jobs: List[Dict] = []
        seen = set()

        for keyword in keywords:
            if len(jobs) >= self.max_jobs:
                break
            try:
                html = self._search(keyword)
            except Exception:
                continue

            soup = BeautifulSoup(html, "lxml")

            # Chercher les offres — structure variable
            for card in soup.select("article, .offer, .job, .offre, .row")[:self.max_jobs]:
                title_el = card.select_one("h2, h3, .title, a")
                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                link = card.select_one("a") if title_el.name != "a" else title_el
                url = link.get("href", "") if link else ""
                if url and not url.startswith("http"):
                    url = f"https://www.emploi-ess.fr{url}" if url.startswith("/") else url

                # Déduplication
                dedup_key = title[:60]
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                # Extraire infos
                company = ""
                location = ""
                contract = ""
                for el in card.select("span, p, div"):
                    txt = el.get_text(strip=True)
                    if not txt:
                        continue
                    if not company and any(k in txt.lower() for k in ["association", "fondation", "coopérative", "mutuelle"]):
                        company = txt[:80]
                    if not location and any(k in txt.lower() for k in ["paris", "lyon", "marseille", "75", "69", "île-de-france"]):
                        location = txt[:50]
                    if not contract and any(k in txt.lower() for k in ["cdi", "cdd", "freelance"]):
                        contract = txt[:30]

                if not company:
                    # Extraire depuis le texte global du container
                    full_text = card.get_text(" ", strip=True)
                    for line in full_text.split("  "):
                        line = line.strip()
                        if not company and any(k in line.lower() for k in ["association", "fondation", "coopérative", "mutuelle", "scop", "scic"]):
                            company = line[:80]

                jobs.append({
                    "title": title,
                    "company": company or "ESS",
                    "location": location or "Île-de-France",
                    "contract_type": contract or None,
                    "salary": None,
                    "description": card.get_text(" ", strip=True)[:800],
                    "url": url,
                    "source": "emploi_ess",
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                })

        return jobs
