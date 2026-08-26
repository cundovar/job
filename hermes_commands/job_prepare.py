from __future__ import annotations

import argparse

from applications import ApplicationTracker, build_application_package
from pipeline import load_criteria

from .utils import get_job_by_number, load_cached_jobs, ranked_jobs


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare une candidature depuis le top du cache.")
    parser.add_argument("number", type=int, help="Numero de l'offre dans le classement top.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--cache", default="data/jobs_cache.json")
    parser.add_argument("--output-dir", default="output/applications")
    parser.add_argument("--tracker", default="data/applications_tracker.json")
    args = parser.parse_args()

    jobs = ranked_jobs(load_cached_jobs(args.cache), limit=args.limit)
    job = get_job_by_number(jobs, args.number)
    criteria = load_criteria()
    package = build_application_package(
        job,
        output_dir=args.output_dir,
        user_profile=criteria.get("user_profile", {}),
    )
    record = ApplicationTracker(args.tracker).mark_ready(job, package)

    print(
        "\n".join(
            [
                "Candidature preparee.",
                "",
                f"Offre : {job.get('title', 'Poste non renseigne')} - {job.get('company', 'Entreprise non renseignee')}",
                f"Score : {job.get('score', 'Non renseigne')}/100",
                f"Variante CV : {package.recommended_cv.cv_name} ({package.recommended_cv.cv_id})",
                "",
                "Documents generes :",
                f"- {package.resume_path}",
                f"- {package.cv_recommendation_path}",
                f"- {package.motivation_letter_path}",
                f"- {package.application_email_path}",
                f"- {package.metadata_path}",
                "",
                f"Statut suivi : {record['status']}",
            ]
        )
    )


if __name__ == "__main__":
    main()
