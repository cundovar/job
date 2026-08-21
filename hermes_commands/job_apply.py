from __future__ import annotations

import argparse

from applications import ApplicationTracker

from .utils import get_job_by_number, load_cached_jobs, ranked_jobs


def main() -> None:
    parser = argparse.ArgumentParser(description="Marque une offre comme postulee.")
    parser.add_argument("number", type=int, help="Numero de l'offre dans le classement top.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--cache", default="data/jobs_cache.json")
    parser.add_argument("--tracker", default="data/applications_tracker.json")
    parser.add_argument("--follow-up-days", type=int, default=7)
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    jobs = ranked_jobs(load_cached_jobs(args.cache), limit=args.limit)
    job = get_job_by_number(jobs, args.number)
    record = ApplicationTracker(args.tracker).mark_applied(
        job,
        follow_up_days=args.follow_up_days,
        notes=args.notes,
    )

    print(
        "\n".join(
            [
                "Candidature marquee comme postulee.",
                "",
                f"Offre : {record['job_title']} - {record['company']}",
                f"Date candidature : {record['applied_at']}",
                f"Relance prevue : {record['follow_up_at']}",
            ]
        )
    )


if __name__ == "__main__":
    main()
