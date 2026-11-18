"""Écarte les offres trop anciennes (critère « publiée depuis moins de 14 jours »).

Ajouté le 18/11/2026 : ``scraping.max_job_age_days`` existait dans
criteria.yaml mais n'était appliqué nulle part. Une date absente ou
illisible ne fait jamais écarter une offre : on ne sait pas, on garde.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional


def parse_published(value: object) -> Optional[date]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:10], fmt).date()
        except ValueError:
            continue
    try:
        return parsedate_to_datetime(raw).date()  # RSS : « Tue, 18 Nov 2026 08:00:00 +0100 »
    except (TypeError, ValueError, IndexError):
        return None


def filter_by_age(jobs: List[Dict], criteria: Dict, today: Optional[date] = None) -> List[Dict]:
    max_days = (criteria.get("scraping") or {}).get("max_job_age_days")
    if not max_days:
        return jobs
    today = today or datetime.now(timezone.utc).date()
    kept = []
    for job in jobs:
        published = parse_published(job.get("published_at"))
        if published is None or (today - published).days <= int(max_days):
            kept.append(job)
    return kept
