from __future__ import annotations

import argparse

from applications import ApplicationTracker

from .utils import load_cached_jobs


def main() -> None:
    parser = argparse.ArgumentParser(description="Affiche un statut simple du cache.")
    parser.add_argument("--cache", default="data/jobs_cache.json")
    parser.add_argument("--tracker", default="data/applications_tracker.json")
    args = parser.parse_args()

    jobs = load_cached_jobs(args.cache)
    records = ApplicationTracker(args.tracker).list_records()
    postuler = sum(1 for job in jobs if job.get("ai_analysis", {}).get("recommandation") == "POSTULER")
    peut_etre = sum(1 for job in jobs if job.get("ai_analysis", {}).get("recommandation") == "PEUT-ÊTRE")
    passer = sum(1 for job in jobs if job.get("ai_analysis", {}).get("recommandation") == "PASSER")
    ready = sum(1 for record in records if record.get("status") == "ready_to_apply")
    applied = sum(1 for record in records if record.get("status") == "applied")
    due = len(ApplicationTracker(args.tracker).due_followups())

    print(
        "\n".join(
            [
                "Statut recherche emploi",
                "",
                f"Offres en cache : {len(jobs)}",
                f"POSTULER : {postuler}",
                f"PEUT-ETRE : {peut_etre}",
                f"PASSER : {passer}",
                f"Candidatures pretes : {ready}",
                f"Candidatures envoyees : {applied}",
                f"Relances a faire : {due}",
                "",
                "Commandes disponibles :",
                "- python3 -m hermes_commands.job_top",
                "- python3 -m hermes_commands.job_prepare 1",
                "- python3 -m hermes_commands.job_apply 1",
                "- python3 -m hermes_commands.job_relance",
                "- python3 -m hermes_commands.job_today",
            ]
        )
    )


if __name__ == "__main__":
    main()
