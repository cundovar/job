"""
Local JSON storage for caching job results.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List


class JSONStorage:
    def __init__(self, path: str = "data/jobs_cache.json", cache_days: int = 30) -> None:
        self.path = Path(path)
        self.cache_days = cache_days
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> List[Dict]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self, jobs: List[Dict]) -> None:
        self.path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")

    def save(self, jobs: List[Dict]) -> None:
        existing = self._load()
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.cache_days)

        def is_recent(job: Dict) -> bool:
            ts = job.get("scraped_at")
            if not ts:
                return True
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00")) >= cutoff
            except Exception:
                return True

        existing = [j for j in existing if is_recent(j)]

        deduped = {(j.get("url") or f"{j.get('title')}-{j.get('company')}"): j for j in existing}
        for job in jobs:
            key = job.get("url") or f"{job.get('title')}-{job.get('company')}"
            deduped[key] = job

        self._save(list(deduped.values()))
