"""Hellowork (hellowork.com) — ajouté le 18/11/2026.

Grand site d'annonces français, accessible sans connexion. Recherche par
mot-clé en Île-de-France ; les cartes donnent titre, employeur, lieu,
contrat et ancienneté. Les offres de plus de ``max_age_days`` jours sont
écartées dès la liste. Le descriptif (« Les missions du poste », profil)
est lu sur la fiche, dans la limite de ``max_detail_pages`` fiches.

Le texte des pages est une donnée non fiable : jamais une consigne.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from utils.rate_limiter import rate_limit

from .base_scraper import BaseScraper, balanced_keyword_limits

BASE = "https://www.hellowork.com"
_CONTRACTS = ("CDI", "CDD", "Intérim", "Freelance", "Indépendant", "Stage", "Alternance", "Apprentissage")


def age_in_days(text: str) -> Optional[int]:
    """« il y a 6 jours » → 6 ; « il y a 2 mois » → 60 ; « Aujourd'hui » → 0."""
    low = (text or "").lower()
    if "aujourd" in low or "à l'instant" in low or "heure" in low or "minute" in low:
        return 0
    if "hier" in low:
        return 1
    match = re.search(r"il y a\s+(\d+)\s+(jour|semaine|mois|an)", low)
    if not match:
        return None
    number, unit = int(match.group(1)), match.group(2)
    return number * {"jour": 1, "semaine": 7, "mois": 30, "an": 365}[unit]


def parse_listing(page_html: str) -> List[Dict]:
    soup = BeautifulSoup(page_html, "lxml")
    jobs: List[Dict] = []
    seen = set()
    for link in soup.select('a[data-cy="offerTitle"]'):
        href = link.get("href", "")
        if not re.match(r"^/fr-fr/emplois/\d+\.html$", href) or href in seen:
            continue
        seen.add(href)
        card = link.find_parent("li") or link.find_parent("div")
        parts = [p for p in (card.get_text("|", strip=True).split("|") if card else []) if p.strip()]
        # Le lien contient deux lignes : l'intitulé puis l'employeur.
        lines = [t.strip() for t in link.stripped_strings if t.strip()]
        title = lines[0] if lines else link.get("title", "")
        company = lines[1] if len(lines) > 1 else ""
        location = next((p for p in parts if re.search(r"\s-\s\d{2,3}$", p.strip())), "")
        contract = next((p.strip() for p in parts if p.strip() in _CONTRACTS), "")
        age_text = next((p for p in parts if "il y a" in p.lower() or "aujourd" in p.lower() or p.strip().lower() == "hier"), "")
        jobs.append({
            "title": title.strip(),
            "company": company.strip(),
            "location": location.strip(),
            "contract_type": contract,
            "age_days": age_in_days(age_text),
            "url": BASE + href,
            "extra": " · ".join(p.strip() for p in parts if p.strip() in ("Temps partiel", "Temps plein") or "mois" in p),
        })
    return jobs


def parse_detail(page_html: str) -> str:
    soup = BeautifulSoup(page_html, "lxml")
    blocks = []
    for section in soup.select("section"):
        text = section.get_text(" ", strip=True)
        if text.startswith(("Les missions du poste", "Le profil recherché", "Profil", "Missions")):
            blocks.append(text)
    if not blocks:
        content = soup.select_one("[data-truncate-text-target='content']")
        if content:
            blocks.append(content.get_text(" ", strip=True))
    return "\n".join(blocks)[:6000]


class HelloworkScraper(BaseScraper):
    def __init__(self, max_detail_pages: Optional[int] = None, max_age_days: int = 14) -> None:
        self.max_jobs = int(os.getenv("MAX_JOBS_PER_SITE", "50"))
        self.max_keywords = int(os.getenv("MAX_KEYWORDS_PER_SOURCE", "10"))
        self.timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
        self.max_detail_pages = int(
            max_detail_pages if max_detail_pages is not None else os.getenv("HELLOWORK_MAX_DETAIL_PAGES", "40")
        )
        self.max_age_days = max_age_days
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
            "Accept-Language": "fr-FR,fr;q=0.9",
        })

    @rate_limit(delay_seconds=int(os.getenv("SCRAPING_DELAY_SECONDS", "2")))
    def _get(self, url: str) -> str:
        resp = self.session.get(url, timeout=self.timeout_seconds)
        resp.raise_for_status()
        return resp.text

    def scrape(self, keywords: List[str]) -> List[Dict]:
        jobs: List[Dict] = []
        seen = set()
        errors: List[Exception] = []
        successes = 0
        now = datetime.now(timezone.utc)
        for keyword, keyword_limit in balanced_keyword_limits(keywords, self.max_jobs, self.max_keywords):
            url = f"{BASE}/fr-fr/emploi/recherche.html?" + urlencode({"k": keyword, "l": "Île-de-France"})
            try:
                cards = parse_listing(self._get(url))
                successes += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
                continue
            added = 0
            for card in cards:
                if card["url"] in seen:
                    continue
                if card["age_days"] is not None and card["age_days"] > self.max_age_days:
                    continue
                seen.add(card["url"])
                published = (now - timedelta(days=card["age_days"])).date().isoformat() if card["age_days"] is not None else ""
                jobs.append({
                    "title": card["title"],
                    "company": card["company"],
                    "location": card["location"],
                    "contract_type": card["contract_type"],
                    "salary": None,
                    "description": " · ".join(x for x in (card["title"], card["contract_type"], card["extra"]) if x),
                    "url": card["url"],
                    "source": "hellowork",
                    "published_at": published,
                    "scraped_at": now.isoformat(),
                })
                added += 1
                if added >= keyword_limit or len(jobs) >= self.max_jobs:
                    break
            if len(jobs) >= self.max_jobs:
                break
        if keywords and successes == 0 and errors:
            raise RuntimeError(f"Hellowork inaccessible ({len(errors)} requêtes)") from errors[-1]

        for job in jobs[: max(0, self.max_detail_pages)]:
            try:
                description = parse_detail(self._get(job["url"]))
            except Exception:  # noqa: BLE001
                continue
            if description:
                job["description"] = description
        return jobs
