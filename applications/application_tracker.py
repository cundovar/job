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

    def _record_base(self, records, job):
        key = self.job_key(job)
        record = records.get(key, {})
        record.setdefault(
            "key", key
        )
        record.setdefault("job_title", job.get("title", ""))
        record.setdefault("company", job.get("company", ""))
        record.setdefault("url", job.get("url", ""))
        record.setdefault("created_at", datetime.now().isoformat())
        return record

    def mark_sent(self, job: Dict[str, Any], send_info: Dict[str, Any]) -> Dict[str, Any]:
        """Journalise un envoi réel vers une entreprise.

        Un record `applied` garde au minimum status, applied_at, follow_up_at,
        job_title, company, key, created_at, updated_at (règle 5 du CLAUDE.md) :
        on ajoute les champs de la boucle de retour, on n'en retire jamais.
        """
        records = self._load()
        now_dt = datetime.now()
        record = self._record_base(records, job)
        record.update(
            {
                "status": "applied",
                "applied_at": now_dt.date().isoformat(),
                "follow_up_at": (now_dt.date() + timedelta(days=7)).isoformat(),
                "send": {
                    "sent_at": now_dt.isoformat(),
                    "outcome": {"reply": None, "interview": None, "rejection_reason": None},
                    **send_info,
                },
                "updated_at": now_dt.isoformat(),
            }
        )
        records[self.job_key(job)] = record
        self._save(records)
        return record

    def mark_send_failed(self, job: Dict[str, Any], error: str) -> Dict[str, Any]:
        """Un échec d'envoi se journalise, pour ne jamais retenter à l'aveugle."""
        records = self._load()
        now_dt = datetime.now()
        record = self._record_base(records, job)
        record.update(
            {
                "status": "send_failed",
                "send": {"attempted_at": now_dt.isoformat(), "error": error},
                "updated_at": now_dt.isoformat(),
            }
        )
        records[self.job_key(job)] = record
        self._save(records)
        return record

    def sent_on(self, day: date) -> int:
        """Nombre d'envois réels partis ce jour — base du quota."""
        return sum(
            1
            for record in self.list_records()
            if str(record.get("send", {}).get("sent_at", "")).startswith(day.isoformat())
        )

    def contact_history(self) -> List[Dict[str, Any]]:
        """Les envois déjà partis, réussis ou ratés — matière de la déduplication.

        Un échec compte : on ne retente jamais à l'aveugle. Le rapprochement
        lui-même n'est pas fait ici, c'est le rôle de duplicate_check.
        """
        return [
            record
            for record in self.list_records()
            if record.get("status") in {"applied", "send_failed"}
        ]

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
