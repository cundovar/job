from __future__ import annotations

import json
import sys
from pathlib import Path

from applications import (
    ApplicationTracker,
    build_application_package,
    rebuild_candidatures_index,
)
from pipeline import load_criteria

PROJECT = Path(__file__).resolve().parents[1]


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Payload JSON invalide: {exc}")

    job = payload.get("job") if isinstance(payload, dict) else None
    if not isinstance(job, dict):
        raise SystemExit("Payload attendu: {\"job\": {...}}")

    criteria = load_criteria()
    package = build_application_package(
        job,
        output_dir="output/applications",
        user_profile=criteria.get("user_profile", {}),
    )
    index_result = rebuild_candidatures_index(
        PROJECT / "output" / "applications",
        PROJECT / "front" / "public" / "data" / "candidatures.json",
    )
    record = ApplicationTracker("data/applications_tracker.json").mark_ready(job, package)

    directory = Path(package.directory)
    result = {
        "ok": True,
        "id": directory.name,
        "directory": package.directory,
        "motivation_letter_path": package.motivation_letter_path,
        "application_email_path": package.application_email_path,
        "cv_name": package.recommended_cv.cv_name,
        "cv_variant": package.recommended_cv.cv_id,
        "record": record,
        "index": index_result,
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
