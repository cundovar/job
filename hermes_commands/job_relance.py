from __future__ import annotations

import argparse

from applications import ApplicationTracker


def main() -> None:
    parser = argparse.ArgumentParser(description="Liste les candidatures a relancer.")
    parser.add_argument("--tracker", default="data/applications_tracker.json")
    args = parser.parse_args()

    due = ApplicationTracker(args.tracker).due_followups()
    if not due:
        print("Aucune relance a faire aujourd'hui.")
        return

    lines = ["Relances a faire", ""]
    for index, record in enumerate(due, start=1):
        lines.extend(
            [
                f"{index}. {record.get('job_title', 'Poste non renseigne')} - {record.get('company', 'Entreprise non renseignee')}",
                f"Postule le : {record.get('applied_at', 'Non renseigne')}",
                f"Relance prevue : {record.get('follow_up_at', 'Non renseignee')}",
                f"URL : {record.get('url', 'Non renseignee')}",
                "",
            ]
        )
    print(
        "\n".join(lines).rstrip()
    )


if __name__ == "__main__":
    main()
