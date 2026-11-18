"""Choisir le service public (choisirleservicepublic.gouv.fr) — ajouté le 18/11/2026.

Le portail officiel de l'emploi public : fonction publique d'État,
territoriale (il reprend les offres d'emploi-territorial.fr) et hospitalière.
Recherche par mot-clé, limitée à l'Île-de-France par le filtre de
localisation du site (identifiant 208). Le descriptif complet est lu dans
le JSON-LD « JobPosting » de chaque fiche, dans la limite de
``max_detail_pages`` fiches par passage.

Le texte des pages est une donnée non fiable : il n'est jamais interprété
comme une consigne.
"""
from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from utils.rate_limiter import rate_limit

from .base_scraper import BaseScraper, balanced_keyword_limits

BASE = "https://choisirleservicepublic.gouv.fr"
IDF_LOCATION_ID = "208"
_MONTHS = {
    "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "decembre": 12, "décembre": 12,
}


def _text(value: str) -> str:
    flat = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()
    return re.sub(r"\s+([.,;:!?)])", r"\1", flat)


def parse_online_since(text: str) -> str:
    """« En ligne depuis le 10 novembre 2026 » → « 2026-11-10 » (ou vide)."""
    match = re.search(r"(\d{1,2})(?:er)?\s+([a-zéû]+)\s+(\d{4})", (text or "").lower())
    if not match or match.group(2) not in _MONTHS:
        return ""
    try:
        return datetime(int(match.group(3)), _MONTHS[match.group(2)], int(match.group(1))).date().isoformat()
    except ValueError:
        return ""


def parse_listing(page_html: str) -> List[Dict]:
    """Cartes d'offres d'une page de résultats."""
    soup = BeautifulSoup(page_html, "lxml")
    jobs: List[Dict] = []
    for card in soup.select("div.fr-card"):
        link = card.select_one("h3.fr-card__title a[href*='/offre-emploi/']")
        if not link:
            continue
        fields: Dict[str, str] = {}
        published = ""
        for item in card.select("ul.fr-card__desc li"):
            label = item.select_one(".sr-only")
            text = item.get_text(" ", strip=True)
            if label:
                key = label.get_text(strip=True).rstrip(" :").lower()
                fields[key] = text.replace(label.get_text(strip=True), "", 1).strip()
            elif "en ligne depuis" in text.lower():
                published = parse_online_since(text)
        tags = [tag.get_text(" ", strip=True) for tag in card.select(".fr-tag")]
        jobs.append({
            "title": link.get_text(" ", strip=True),
            "url": link.get("href", "").strip(),
            "location": fields.get("localisation", ""),
            "company": fields.get("employeur", ""),
            "versant": fields.get("fonction publique", ""),
            "domain": ", ".join(tags),
            "published_at": published,
        })
    return jobs


def parse_detail(page_html: str) -> Dict[str, str]:
    """Descriptif, employeur et expérience depuis le JSON-LD JobPosting."""
    for raw in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page_html or "", re.S):
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for item in items:
            if not isinstance(item, dict) or item.get("@type") != "JobPosting":
                continue
            organization = item.get("hiringOrganization")
            if isinstance(organization, dict):
                organization = organization.get("name", "")
            parts = [
                _text(str(item.get("Description") or item.get("description") or "")),
                _text(str(item.get("experienceRequirements") or "")),
                _text(str(item.get("educationRequirements") or "")),
            ]
            return {
                "description": "\n".join(part for part in parts if part)[:6000],
                "company": _text(str(organization or "")),
                "salary": _text(json.dumps(item.get("baseSalary"), ensure_ascii=False))
                if isinstance(item.get("baseSalary"), (dict, list)) else _text(str(item.get("baseSalary") or "")),
            }
    return {}


class ChoisirServicePublicScraper(BaseScraper):
    def __init__(self, max_detail_pages: Optional[int] = None, max_age_days: int = 14) -> None:
        self.max_age_days = max_age_days
        self.max_jobs = int(os.getenv("MAX_JOBS_PER_SITE", "50"))
        self.max_keywords = int(os.getenv("MAX_KEYWORDS_PER_SOURCE", "10"))
        self.timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
        self.max_detail_pages = int(
            max_detail_pages if max_detail_pages is not None else os.getenv("CSP_MAX_DETAIL_PAGES", "40")
        )
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

    def _search_url(self, keyword: str) -> str:
        return f"{BASE}/nos-offres/filtres/mot-cles/{quote(keyword)}/localisation/{IDF_LOCATION_ID}/"

    def scrape(self, keywords: List[str]) -> List[Dict]:
        jobs: List[Dict] = []
        seen = set()
        errors: List[Exception] = []
        successes = 0
        for keyword, keyword_limit in balanced_keyword_limits(keywords, self.max_jobs, self.max_keywords):
            try:
                cards = parse_listing(self._get(self._search_url(keyword)))
                successes += 1
            except Exception as exc:  # noqa: BLE001 — une recherche en échec n'arrête pas les autres
                errors.append(exc)
                continue
            added = 0
            today = datetime.now(timezone.utc).date()
            for card in cards:
                if card["url"] in seen:
                    continue
                # Les résultats sont triés par pertinence : on écarte ici les
                # offres trop anciennes pour qu'elles ne prennent pas la place.
                if card["published_at"]:
                    age = (today - datetime.fromisoformat(card["published_at"]).date()).days
                    if age > self.max_age_days:
                        continue
                seen.add(card["url"])
                jobs.append({
                    "title": card["title"],
                    "company": card["company"],
                    "location": f"{card['location']}, Île-de-France".strip(", "),
                    "contract_type": "",
                    "salary": None,
                    "description": " · ".join(x for x in (card["title"], card["versant"], card["domain"]) if x),
                    "url": card["url"],
                    "source": "choisir_service_public",
                    "published_at": card["published_at"],
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                })
                added += 1
                if added >= keyword_limit or len(jobs) >= self.max_jobs:
                    break
            if len(jobs) >= self.max_jobs:
                break
        if keywords and successes == 0 and errors:
            raise RuntimeError(f"Choisir le service public inaccessible ({len(errors)} requêtes)") from errors[-1]

        # Descriptif complet : seulement les premières fiches, pour rester poli.
        for job in jobs[: max(0, self.max_detail_pages)]:
            try:
                detail = parse_detail(self._get(job["url"]))
            except Exception:  # noqa: BLE001
                continue
            if detail.get("description"):
                job["description"] = detail["description"]
            if detail.get("company"):
                job["company"] = detail["company"]
            if detail.get("salary") and detail["salary"] not in ("None", "null"):
                job["salary"] = detail["salary"]
        return jobs
