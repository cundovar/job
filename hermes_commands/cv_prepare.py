from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

load_dotenv()

from cv_generator import prepare_custom_cv
from hermes_commands.utils import get_job_by_number, load_cached_jobs, ranked_jobs


def _load_job_from_application_dir(application_dir: Path) -> Dict[str, Any]:
    # New application packages keep the full structured offer. This is the
    # preferred source for the AI agents.
    job_path = application_dir / "job.json"
    if job_path.exists():
        job = json.loads(job_path.read_text(encoding="utf-8"))
        if isinstance(job, dict):
            return job

    metadata_path = application_dir / "metadata.json"
    if not metadata_path.exists():
        raise SystemExit(f"metadata.json introuvable dans {application_dir}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    # Backfill old application packages from the full jobs cache when possible.
    cache_path = Path("data/jobs_cache.json")
    if cache_path.exists():
        try:
            cached_jobs = json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cached_jobs = []
        if isinstance(cached_jobs, list):
            target_url = str(metadata.get("url") or "").strip()
            target_title = str(metadata.get("job_title") or "").strip().casefold()
            target_company = str(metadata.get("company") or "").strip().casefold()
            for cached in cached_jobs:
                if not isinstance(cached, dict):
                    continue
                same_url = target_url and str(cached.get("url") or "").strip() == target_url
                same_identity = (
                    target_title
                    and target_company
                    and str(cached.get("title") or "").strip().casefold() == target_title
                    and str(cached.get("company") or "").strip().casefold() == target_company
                )
                if same_url or same_identity:
                    return cached

    # Last-resort compatibility for old packages no longer present in the cache.
    job = {
        "title": metadata.get("job_title"),
        "company": metadata.get("company"),
        "score": metadata.get("score"),
        "source": metadata.get("source"),
        "url": metadata.get("url"),
    }
    resume = application_dir / "offre_resume.md"
    if resume.exists():
        job["description"] = resume.read_text(encoding="utf-8")
        job["_source_warning"] = "Annonce complète indisponible: utilisation du résumé historique."
    return job

def _load_job_from_payload(payload_path: Path) -> Dict[str, Any]:
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("job"), dict):
        return payload["job"]
    if isinstance(payload, dict):
        return payload
    raise SystemExit("Payload JSON invalide: attendu objet job ou {\"job\": {...}}")


def _default_application_dir(job: Dict[str, Any]) -> Path:
    safe = "".join(ch if ch.isalnum() else "-" for ch in f"{job.get('company','entreprise')}-{job.get('title','poste')}".lower())
    safe = "-".join(part for part in safe.split("-") if part)[:90] or "cv-personnalise"
    return Path("output/applications") / safe


def main() -> None:
    parser = argparse.ArgumentParser(description="Genere un CV personnalise pour une candidature.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--application-dir", help="Dossier output/applications/... contenant metadata.json")
    source.add_argument("--job-json", help="Fichier JSON contenant l'offre ou {job: ...}")
    source.add_argument("--number", type=int, help="Numero de l'offre dans le classement du cache")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--cache", default="data/jobs_cache.json")
    parser.add_argument("--master", default="data/cv_master_profile.json")
    parser.add_argument("--output-dir", help="Dossier candidature cible si --job-json ou --number")
    args = parser.parse_args()

    if args.application_dir:
        application_dir = Path(args.application_dir)
        job = _load_job_from_application_dir(application_dir)
    elif args.job_json:
        job = _load_job_from_payload(Path(args.job_json))
        application_dir = Path(args.output_dir) if args.output_dir else _default_application_dir(job)
        application_dir.mkdir(parents=True, exist_ok=True)
    else:
        jobs = ranked_jobs(load_cached_jobs(args.cache), limit=args.limit)
        job = get_job_by_number(jobs, args.number)
        application_dir = Path(args.output_dir) if args.output_dir else _default_application_dir(job)
        application_dir.mkdir(parents=True, exist_ok=True)

    result = prepare_custom_cv(job, application_dir=application_dir, master_path=args.master)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
