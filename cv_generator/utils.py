from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List


def load_json(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path: str | Path, data: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize(value: Any) -> str:
    raw = str(value or "")
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", raw)
        if not unicodedata.combining(char)
    )
    lowered = without_accents.lower()
    return re.sub(r"\s+", " ", lowered).strip()


def job_text(job: Dict[str, Any]) -> str:
    parts = []
    for key in ("title", "company", "description", "requirements", "sector", "contract_type", "location"):
        value = job.get(key)
        if value:
            parts.append(str(value))
    analysis = job.get("ai_analysis")
    if isinstance(analysis, dict):
        for key in ("points_forts", "points_faibles", "red_flags", "angle_motivation", "raison_breve"):
            value = analysis.get(key)
            if isinstance(value, list):
                parts.extend(str(item) for item in value)
            elif value:
                parts.append(str(value))
    return normalize(" ".join(parts))


def contains_any(text: str, keywords: Iterable[str]) -> bool:
    norm_keywords = [normalize(keyword) for keyword in keywords]
    return any(keyword and keyword in text for keyword in norm_keywords)


def experience_visible_for_job(experience: Dict[str, Any], job: Dict[str, Any]) -> bool:
    """Enforce catalogue visibility before an experience reaches the CV."""
    visibility = str(experience.get("visibility") or "default")
    if not visibility.startswith("only_"):
        return True
    triggers = experience.get("explicit_job_triggers")
    if not isinstance(triggers, list):
        triggers = experience.get("selection_triggers", experience.get("tags", []))
    return contains_any(job_text(job), triggers if isinstance(triggers, list) else [])


def compact_items(items: Iterable[str], limit: int, max_chars: int | None = None) -> List[str]:
    result: List[str] = []
    seen = set()
    for item in items:
        cleaned = re.sub(r"\s+", " ", str(item or "")).strip()
        if not cleaned:
            continue
        if max_chars and len(cleaned) > max_chars:
            cleaned = cleaned[: max_chars - 1].rstrip(" ,;:") + "…"
        key = normalize(cleaned)
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
        if len(result) >= limit:
            break
    return result


def period_to_text(period: Dict[str, Any] | None) -> str:
    if not isinstance(period, dict):
        return ""
    start = period.get("start") or ""
    end = period.get("end") or "Aujourd'hui"
    if not start and not period.get("end"):
        return ""
    return f"{start} – {end}"


def flatten_skills(skills: Dict[str, Any]) -> List[str]:
    flat: List[str] = []
    for value in skills.values():
        if isinstance(value, list):
            flat.extend(str(item) for item in value)
    return flat
