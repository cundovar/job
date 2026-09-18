from __future__ import annotations

import argparse

from pipeline_spontaneous import CACHE_PATH, prepare_application, run_spontaneous_search

from .company_top import load_cached_companies


def usable_companies(results):
    return [result for result in results if result.get("opportunity")]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare une candidature spontanee depuis le cache de prospection."
    )
    parser.add_argument("number", type=int, help="Numero de l'entreprise dans la liste exploitable.")
    parser.add_argument("--cache", default=str(CACHE_PATH))
    parser.add_argument(
        "--refresh", action="store_true", help="Relance les mesures au lieu de lire le cache."
    )
    parser.add_argument("--no-ai", action="store_true")
    parser.add_argument("--no-cv", action="store_true", help="Ne pas generer le CV adapte.")
    args = parser.parse_args()

    results = load_cached_companies(args.cache)
    if args.refresh or not results:
        results = run_spontaneous_search(use_ai=not args.no_ai)

    usable = usable_companies(results)
    if args.number < 1 or args.number > len(usable):
        raise SystemExit(
            f"Entreprise {args.number} introuvable. Exploitables : {len(usable)}"
        )

    payload = prepare_application(usable[args.number - 1], with_cv=not args.no_cv)

    lines = [
        "Candidature spontanee preparee.",
        "",
        f"Structure : {payload['company']}",
        f"Poste vise : {payload['title']}",
        f"Constats confirmes : {payload['confirmed_findings']}",
        f"Variante CV : {payload['recommended_cv']}",
        "",
        "Documents generes :",
        f"- {payload['files']['resume']}",
        f"- {payload['files']['motivation_letter']}",
        f"- {payload['files']['application_email']}",
        f"- {payload['files']['metadata']}",
    ]

    cv = payload.get("cv")
    if cv:
        lines.extend(
            [
                "",
                f"CV adapte : {cv['status']} (qualite {cv['quality_score']}, ATS {cv['ats_score']})",
                f"- {cv['cv_dir']}",
            ]
        )

    lines.extend(["", "Aucun envoi. Le dossier reste local, a valider par vous."])
    print("\n".join(lines))


if __name__ == "__main__":
    main()
