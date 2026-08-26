from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from applications import ApplicationTracker, build_application_package
from pipeline import load_criteria

PROJECT = Path(__file__).resolve().parents[1]
HERMES_HOME = Path(os.getenv("HERMES_HOME", "/data/hermes"))
INDEX_SCRIPT = HERMES_HOME / "scripts" / "job_search_json_candidatures.py"


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
    record = ApplicationTracker("data/applications_tracker.json").mark_ready(job, package)

    index_result = subprocess.run(
        ["python3", str(INDEX_SCRIPT)],
        cwd=PROJECT,
        text=True,
        capture_output=True,
        check=False,
    )
    if index_result.returncode != 0:
        raise SystemExit(index_result.stderr or index_result.stdout or "Erreur génération index candidatures")

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
        "index": json.loads(index_result.stdout.strip() or "{}"),
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
