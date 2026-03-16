"""
Local JSON storage for caching job results.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List


class JSONStorage:
    def __init__(
        self,
        path: str = "data/jobs_cache.json",
        cache_days: int = 30,
        sent_path: str = "data/sent_jobs.json",
    ) -> None:
        self.path = Path(path)
        self.sent_path = Path(sent_path)
        self.cache_days = cache_days
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.sent_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> List[Dict]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _load_sent(self) -> List[Dict]:
        if not self.sent_path.exists():
            return []
        try:
            return json.loads(self.sent_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self, jobs: List[Dict]) -> None:
        self.path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")

    def _save_sent(self, sent_jobs: List[Dict]) -> None:
        self.sent_path.write_text(json.dumps(sent_jobs, ensure_ascii=False, indent=2), encoding="utf-8")

    def _job_key(self, job: Dict) -> str:
        return job.get("url") or f"{job.get('title', '')}-{job.get('company', '')}"

    def _is_recent(self, item: Dict, field_name: str, cutoff: datetime) -> bool:
        ts = item.get(field_name)
        if not ts:
            return True
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")) >= cutoff
        except Exception:
            return True

    def save(self, jobs: List[Dict]) -> None:
        existing = self._load()
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.cache_days)
        existing = [j for j in existing if self._is_recent(j, "scraped_at", cutoff)]
        deduped = {self._job_key(j): j for j in existing}
        for job in jobs:
            deduped[self._job_key(job)] = job

        self._save(list(deduped.values()))

    def get_unsent_jobs(self, jobs: List[Dict]) -> List[Dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.cache_days)
        sent_jobs = [j for j in self._load_sent() if self._is_recent(j, "sent_at", cutoff)]
        sent_keys = {item.get("key") for item in sent_jobs if item.get("key")}
        return [job for job in jobs if self._job_key(job) not in sent_keys]

    def mark_jobs_as_sent(self, jobs: List[Dict]) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.cache_days)
        sent_jobs = [j for j in self._load_sent() if self._is_recent(j, "sent_at", cutoff)]
        deduped = {item.get("key"): item for item in sent_jobs if item.get("key")}
        sent_at = datetime.now(timezone.utc).isoformat()

        for job in jobs:
            key = self._job_key(job)
            deduped[key] = {
                "key": key,
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "url": job.get("url", ""),
                "sent_at": sent_at,
            }

        self._save_sent(list(deduped.values()))
