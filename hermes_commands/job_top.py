from __future__ import annotations

import argparse

from .utils import format_job_list, load_cached_jobs, ranked_jobs


def main() -> None:
    parser = argparse.ArgumentParser(description="Affiche les meilleures offres du cache.")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--cache", default="data/jobs_cache.json")
    args = parser.parse_args()

    jobs = ranked_jobs(load_cached_jobs(args.cache), limit=args.limit)
    print(format_job_list(jobs, title=f"Top {len(jobs)} offres"))


if __name__ == "__main__":
    main()
