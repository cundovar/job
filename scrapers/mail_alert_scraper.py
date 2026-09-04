"""
Mail alert scraper: extracts job offers from job-alert emails (IMAP, read-only).

Les alertes Indeed et makesense contiennent deja titre, societe, lieu, salaire et
un extrait de description : inutile de suivre les liens trackes (Indeed est de
toute facon derriere un captcha Cloudflare). Les offres sont donc marquees
description_truncated pour que le juge IA ne penalise pas les infos absentes.

La boite est ouverte en readonly et les messages lus en BODY.PEEK : rien n'est
marque comme lu, deplace ou supprime.
"""
from __future__ import annotations

import collections
import email
import email.header
import email.utils
import imaplib
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List

from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)

INDEED_JOB_URL = re.compile(r"https://[\w.]*indeed\.com/rc/clk[^\s>）)]*")
INDEED_JK = re.compile(r"[?&]jk=([0-9a-f]+)")
MAKESENSE_JOB = re.compile(
    r"^(?P<title>.+?)\s*\(\s*(?P<url>https://jobs\.makesense\.org/jobs/[^\s)]+)\s*\)\s*$"
)
AGE_LINE = re.compile(r"il y a (\d+)\s*(jour|jours|heure|heures)|aujourd.hui|instant", re.I)
SALARY_LINE = re.compile(r"€|EUR|par an|par mois|par heure", re.I)
BADGES = {
    "employeur réactif", "candidature simplifiée", "nouveau",
    "réponse rapide", "urgent", "postulez rapidement",
}


class MailAlertScraper(BaseScraper):
    """Lit les alertes emploi recues par mail et en extrait les offres."""

    SENDERS = ("jobalert.indeed.com", "match.indeed.com", "jobs@makesense.org")

    def __init__(self) -> None:
        self.host = os.getenv("IMAP_HOST", "")
        self.port = int(os.getenv("IMAP_PORT", "993"))
        self.user = os.getenv("IMAP_USER", "")
        self.password = os.getenv("IMAP_PASSWORD", "")
        self.days = int(os.getenv("MAIL_ALERT_DAYS", "7"))
        self.max_jobs = int(os.getenv("MAIL_ALERT_MAX_JOBS", "60"))

    # ── plumbing ────────────────────────────────────────────────────────────
    def _connect(self) -> imaplib.IMAP4_SSL | None:
        if not (self.host and self.user and self.password):
            logger.warning("MailAlertScraper: IMAP non configure, source ignoree")
            return None
        box = imaplib.IMAP4_SSL(self.host, self.port, timeout=30)
        box.login(self.user, self.password)
        box.select("INBOX", readonly=True)
        return box

    @staticmethod
    def _decode(value: str | None) -> str:
        if not value:
            return ""
        chunks = []
        for text, charset in email.header.decode_header(value):
            if isinstance(text, bytes):
                chunks.append(text.decode(charset or "utf-8", errors="replace"))
            else:
                chunks.append(text)
        return "".join(chunks).replace("\n", " ").strip()

    @staticmethod
    def _plain_text(msg) -> str:
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                payload = part.get_payload(decode=True) or b""
                return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        return ""

    @staticmethod
    def _published_at(age_text: str, received: datetime) -> str:
        match = AGE_LINE.search(age_text or "")
        if not match:
            return received.isoformat()
        if match.group(1) and match.group(2):
            amount = int(match.group(1))
            delta = timedelta(days=amount) if match.group(2).startswith("jour") else timedelta(hours=amount)
            return (received - delta).isoformat()
        return received.isoformat()

    # ── parsing Indeed ──────────────────────────────────────────────────────
    def _parse_indeed(self, text: str, received: datetime) -> List[Dict]:
        jobs: List[Dict] = []
        pieces = INDEED_JOB_URL.split(text)
        urls = INDEED_JOB_URL.findall(text)
        for block, url in zip(pieces, urls):
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            # couper l'en-tete du mail (ou la fin du bloc precedent)
            for index in range(len(lines) - 1, -1, -1):
                if "http" in lines[index]:
                    lines = lines[index + 1:]
                    break
            lines = [line for line in lines if line.lower() not in BADGES]
            if len(lines) < 2:
                continue

            age = ""
            if AGE_LINE.search(lines[-1]):
                age = lines.pop()
            title = lines[0]
            company, location = "", ""
            if len(lines) > 1 and " - " in lines[1]:
                company, _, location = lines[1].rpartition(" - ")
            elif len(lines) > 1:
                company = lines[1]
            salary = next((line for line in lines[2:] if SALARY_LINE.search(line)), "")
            description = " ".join(
                line for line in lines[2:] if line != salary
            ).strip()

            jobs.append({
                "title": title,
                "company": company,
                "location": location,
                "contract_type": "",
                "salary": salary,
                "description": description,
                "url": url,
                "external_id": (INDEED_JK.search(url) or [None, ""])[1] if INDEED_JK.search(url) else "",
                "description_truncated": True,
                "source": "mail_indeed",
                "published_at": self._published_at(age, received),
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            })
        return jobs

    # ── parsing makesense ───────────────────────────────────────────────────
    def _parse_makesense(self, text: str, received: datetime) -> List[Dict]:
        jobs: List[Dict] = []
        lines = [line.strip() for line in text.splitlines()]
        for index, line in enumerate(lines):
            match = MAKESENSE_JOB.match(line)
            if not match:
                continue
            company = next(
                (lines[j] for j in range(index - 1, max(index - 4, -1), -1) if lines[j]),
                "",
            )
            following = [value for value in lines[index + 1: index + 4] if value]
            description = following[0] if following else ""
            meta = following[1] if len(following) > 1 else ""
            contract, meta = self._split_contract(meta)
            url = match.group("url").split("?")[0]
            jobs.append({
                "title": match.group("title").strip(),
                "company": company,
                "location": meta,
                "contract_type": contract,
                "salary": "",
                "description": description,
                "url": url,
                "external_id": url.rsplit("/", 1)[-1],
                "description_truncated": True,
                "source": "mail_makesense",
                "published_at": received.isoformat(),
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            })
        return jobs

    # ── entree publique ─────────────────────────────────────────────────────
    def scrape(self, keywords: List[str]) -> List[Dict]:
        """keywords est ignore : les alertes sont deja filtrees a la source."""
        try:
            box = self._connect()
        except Exception as exc:
            logger.warning(f"MailAlertScraper: connexion impossible ({exc})")
            return []
        if box is None:
            return []

        jobs: List[Dict] = []
        seen: set[str] = set()
        per_source: Dict[str, int] = collections.defaultdict(int)
        since = (datetime.now() - timedelta(days=self.days)).strftime("%d-%b-%Y")
        try:
            for sender in self.SENDERS:
                typ, data = box.search(None, f'(SINCE {since} FROM "{sender}")')
                for num in reversed((data[0] or b"").split()):
                    typ, raw = box.fetch(num, "(BODY.PEEK[])")
                    if not raw or not isinstance(raw[0], tuple):
                        continue
                    msg = email.message_from_bytes(raw[0][1])
                    received = self._received_at(msg)
                    text = self._plain_text(msg)
                    if not text:
                        continue
                    found = (
                        self._parse_makesense(text, received)
                        if "makesense" in sender
                        else self._parse_indeed(text, received)
                    )
                    for job in found:
                        key = job.get("external_id") or job.get("url", "")
                        if not key or key in seen or not job.get("title"):
                            continue
                        seen.add(key)
                        jobs.append(job)
                        per_source[job["source"]] += 1
                    if per_source[self._source_of(sender)] >= self.max_jobs:
                        break
        finally:
            try:
                box.logout()
            except Exception:
                pass

        logger.info(f"MailAlertScraper: {len(jobs)} jobs")
        return jobs

    # makesense colle le type de contrat au lieu : "AlternanceParis, France"
    CONTRACTS = ("CDI", "CDD", "Alternance", "Freelance", "Stage",
                 "Service Civique", "Bénévolat", "Volontariat")

    @classmethod
    def _split_contract(cls, meta: str) -> tuple[str, str]:
        for label in cls.CONTRACTS:
            if meta.lower().startswith(label.lower()):
                return label, meta[len(label):].strip(" ·,-")
        return "", meta

    @staticmethod
    def _source_of(sender: str) -> str:
        return "mail_makesense" if "makesense" in sender else "mail_indeed"

    @staticmethod
    def _received_at(msg) -> datetime:
        try:
            parsed = email.utils.parsedate_to_datetime(msg.get("Date"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)
