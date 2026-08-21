from __future__ import annotations

import argparse

from pipeline import run_job_search

from .utils import format_job_list, ranked_jobs


def main() -> None:
    parser = argparse.ArgumentParser(description="Lance la recherche du jour.")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument(
        "--send-outputs",
        action="store_true",
        help="Autorise les sorties email/Google Sheets. Desactive par defaut pour Hermes.",
    )
    args = parser.parse_args()

    result = run_job_search(send_outputs=args.send_outputs)
    stats = result["stats"]
    top_jobs = ranked_jobs(result["jobs"], limit=args.limit)

    print(
        "\n".join(
            [
                "Recherche du jour terminee.",
                "",
                f"Offres scrapees : {result['all_jobs_count']}",
                f"Offres filtrees : {stats['total']}",
                f"POSTULER : {stats['postuler']}",
                f"PEUT-ETRE : {stats['peut_etre']}",
                f"PASSER : {stats['passer']}",
                "",
                format_job_list(top_jobs, title=f"Top {len(top_jobs)} offres"),
            ]
        )
    )


if __name__ == "__main__":
    main()
