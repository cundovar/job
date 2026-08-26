"""Build the static candidature index from application packages."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


PARIS_TIMEZONE = ZoneInfo("Europe/Paris")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _read_metadata(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def _format_created_at(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    try:
        created_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if created_at.tzinfo is not None:
        created_at = created_at.astimezone(PARIS_TIMEZONE)
    return created_at.strftime("%Y-%m-%d %H:%M")


def _format_cv_recommendation(metadata: dict[str, Any]) -> str:
    recommendation = metadata.get("recommended_cv")
    if not isinstance(recommendation, dict):
        return ""

    lines = []
    cv_name = recommendation.get("cv_name")
    if cv_name:
        lines.append(f"CV conseillé : {cv_name}")
    score = recommendation.get("score")
    if score is not None:
        lines.append(f"Score de correspondance : {score}")
    keywords = recommendation.get("matched_keywords")
    if isinstance(keywords, list) and keywords:
        lines.append(f"Mots-clés détectés : {', '.join(map(str, keywords))}")
    return "\n".join(lines)


def _build_entry(application_dir: Path) -> dict[str, Any] | None:
    metadata = _read_metadata(application_dir / "metadata.json")
    letter_path = application_dir / "lettre_motivation.md"
    email_path = application_dir / "mail_candidature.md"
    if metadata is None or not letter_path.is_file() or not email_path.is_file():
        return None

    legacy_cv_path = application_dir / "cv_recommande.txt"
    cv_recommendation = _read_text(legacy_cv_path)
    if not cv_recommendation:
        cv_recommendation = _format_cv_recommendation(metadata)

    created_at = _format_created_at(metadata.get("created_at"))
    date = application_dir.name[:10]
    if len(date) != 10 or date[4:5] != "-" or date[7:8] != "-":
        date = created_at[:10]

    return {
        "id": application_dir.name,
        "date": date,
        "entreprise": str(metadata.get("company") or ""),
        "poste": str(metadata.get("job_title") or ""),
        "lettre": _read_text(letter_path),
        "mail": _read_text(email_path),
        "cv_recommande": cv_recommendation,
        "created_at": created_at,
        "metadata": metadata,
    }


def rebuild_candidatures_index(
    applications_dir: str | Path,
    index_path: str | Path,
) -> dict[str, Any]:
    """Rebuild ``candidatures.json`` and replace it atomically."""
    source = Path(applications_dir)
    destination = Path(index_path)
    entries = []
    if source.is_dir():
        for application_dir in source.iterdir():
            if not application_dir.is_dir():
                continue
            entry = _build_entry(application_dir)
            if entry is not None:
                entries.append(entry)

    entries.sort(
        key=lambda entry: (entry.get("created_at", ""), entry["id"]),
        reverse=True,
    )
    payload = {"candidatures": entries}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination_mode = (
        destination.stat().st_mode & 0o777 if destination.exists() else 0o644
    )

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            json.dump(payload, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.chmod(temporary_path, destination_mode)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    return {"ok": True, "total": len(entries)}
