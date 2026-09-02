"""
Emploi-territorial RSS scraper.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, List
import re
from xml.etree import ElementTree

import requests

from utils.rate_limiter import rate_limit
from .base_scraper import BaseScraper


class EmploiTerritorialRssScraper(BaseScraper):
    DEFAULT_RSS_URL = "https://www.emploi-territorial.fr/rss/"

    def __init__(self) -> None:
        self.rss_urls = self._load_urls()
        self.max_jobs = int(os.getenv("MAX_JOBS_PER_SITE", "50"))
        self.timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
        self.allowed_depts = self._load_allowed_depts()

    def _load_urls(self) -> List[str]:
        urls = []
        raw = os.getenv("EMPLOI_TERRITORIAL_RSS_URLS", "")
        if raw:
            urls.extend([u.strip() for u in raw.split(",") if u.strip()])
        single = os.getenv("EMPLOI_TERRITORIAL_RSS_URL", "").strip()
        if single:
            urls.append(single)
        return urls or [self.DEFAULT_RSS_URL]

    def _load_allowed_depts(self) -> List[str]:
        raw = os.getenv("EMPLOI_TERRITORIAL_ALLOWED_DEPTS", "")
        return [d.strip() for d in raw.split(",") if d.strip()]

    def _extract_dept(self, text: str) -> str | None:
        if not text:
            return None
        match = re.search(r"O(\d{3})", text)
        return match.group(1) if match else None

    def _dept_allowed(self, job: Dict) -> bool:
        if not self.allowed_depts:
            return True
        dept = self._extract_dept(job.get("id", "")) or self._extract_dept(job.get("url", ""))
        if not dept:
            return False
        return dept in self.allowed_depts

    @rate_limit(delay_seconds=int(os.getenv("SCRAPING_DELAY_SECONDS", "2")))
    def _fetch_feed(self, url: str) -> str:
        resp = requests.get(url, timeout=self.timeout_seconds)
        resp.raise_for_status()
        return resp.text

    def _parse_rss(self, xml_text: str) -> List[Dict]:
        jobs: List[Dict] = []
        root = ElementTree.fromstring(xml_text)

        # RSS 2.0
        channel = root.find("channel")
        if channel is not None:
            items = channel.findall("item")
            for item in items:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                description = (item.findtext("description") or "").strip()
                pub_date = (item.findtext("pubDate") or "").strip()
                guid = (item.findtext("guid") or "").strip()
                jobs.append(
                    {
                        "title": title,
                        "company": "",
                        "location": "",
                        "contract_type": "",
                        "salary": None,
                        "description": description,
                        "url": link,
                        "source": "emploi_territorial_rss",
                        "scraped_at": datetime.now(timezone.utc).isoformat(),
                        "published_at": pub_date,
                        "id": guid,
                    }
                )
            return jobs

        # Atom
        if root.tag.endswith("feed"):
            for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
                title = (entry.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
                link_el = entry.find("{http://www.w3.org/2005/Atom}link")
                link = link_el.get("href", "") if link_el is not None else ""
                summary = (entry.findtext("{http://www.w3.org/2005/Atom}summary") or "").strip()
                published = (entry.findtext("{http://www.w3.org/2005/Atom}published") or "").strip()
                entry_id = (entry.findtext("{http://www.w3.org/2005/Atom}id") or "").strip()
                jobs.append(
                    {
                        "title": title,
                        "company": "",
                        "location": "",
                        "contract_type": "",
                        "salary": None,
                        "description": summary,
                        "url": link,
                        "source": "emploi_territorial_rss",
                        "scraped_at": datetime.now(timezone.utc).isoformat(),
                        "published_at": published,
                        "id": entry_id,
                    }
                )
        return jobs

    def scrape(self, keywords: List[str]) -> List[Dict]:
        if not self.rss_urls:
            raise ValueError("Missing EMPLOI_TERRITORIAL_RSS_URL(S)")

        jobs: List[Dict] = []
        seen_urls = set()

        for url in self.rss_urls:
            xml_text = self._fetch_feed(url)
            feed_jobs = self._parse_rss(xml_text)
            for job in feed_jobs:
                if not self._dept_allowed(job):
                    continue
                job_url = job.get("url")
                if job_url and job_url in seen_urls:
                    continue
                if job_url:
                    seen_urls.add(job_url)
                jobs.append(job)
                if len(jobs) >= self.max_jobs:
                    return jobs

        return jobs
