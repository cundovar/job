"""
Track application status and follow-ups in local JSON.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List


class ApplicationTracker:
    def __init__(self, path: str = "data/applications_tracker.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, records: Dict[str, Dict[str, Any]]) -> None:
        self.path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    def job_key(self, job: Dict[str, Any]) -> str:
        return str(job.get("url") or f"{job.get('title', '')}-{job.get('company', '')}")

    def mark_ready(
        self,
        job: Dict[str, Any],
        package: Any,
    ) -> Dict[str, Any]:
        records = self._load()
        key = self.job_key(job)
        now = datetime.now().isoformat()
        record = records.get(key, {})
        record.update(
            {
                "key": key,
                "status": "ready_to_apply",
                "job_title": job.get("title", ""),
                "company": job.get("company", ""),
                "url": job.get("url", ""),
                "score": job.get("score"),
                "cv_used": package.recommended_cv.cv_id,
                "application_dir": package.directory,
                "letter_path": package.motivation_letter_path,
                "email_path": package.application_email_path,
                "metadata_path": package.metadata_path,
                "updated_at": now,
            }
        )
        record.setdefault("created_at", now)
        records[key] = record
        self._save(records)
        return record

    def mark_applied(
        self,
        job: Dict[str, Any],
        follow_up_days: int = 7,
        notes: str = "",
    ) -> Dict[str, Any]:
        records = self._load()
        key = self.job_key(job)
        now_dt = datetime.now()
        record = records.get(key, {})
        record.update(
            {
                "key": key,
                "status": "applied",
                "job_title": job.get("title", record.get("job_title", "")),
                "company": job.get("company", record.get("company", "")),
                "url": job.get("url", record.get("url", "")),
                "score": job.get("score", record.get("score")),
                "applied_at": now_dt.date().isoformat(),
                "follow_up_at": (now_dt.date() + timedelta(days=follow_up_days)).isoformat(),
                "notes": notes or record.get("notes", ""),
                "updated_at": now_dt.isoformat(),
            }
        )
        record.setdefault("created_at", now_dt.isoformat())
        records[key] = record
        self._save(records)
        return record

    def list_records(self) -> List[Dict[str, Any]]:
        return list(self._load().values())

    def due_followups(self, today: date | None = None) -> List[Dict[str, Any]]:
        today = today or date.today()
        due = []
        for record in self.list_records():
            if record.get("status") != "applied":
                continue
            follow_up_at = record.get("follow_up_at")
            if not follow_up_at:
                continue
            try:
                follow_up_date = date.fromisoformat(follow_up_at)
            except ValueError:
                continue
            if follow_up_date <= today:
                due.append(record)
        return sorted(due, key=lambda item: item.get("follow_up_at", ""))
