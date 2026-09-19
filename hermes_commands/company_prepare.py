from __future__ import annotations

import argparse
from pathlib import Path

from applications import rebuild_candidatures_index
from pipeline_spontaneous import CACHE_PATH, prepare_application, run_spontaneous_search

from .company_top import load_cached_companies

PROJECT = Path(__file__).resolve().parents[1]


def usable_companies(results):
    return [result for result in results if result.get("opportunity")]


def prepare_numbered_application(number, results, with_cv: bool = True):
    """Prépare le dossier N et le rend visible du front de validation.

    Point d'entrée unique de la CLI et de l'outil MCP. Les deux passaient
    auparavant par leur propre copie, et seule celle de la CLI reconstruisait
    l'index : un dossier préparé par Hermes existait sur le disque mais restait
    invisible du front — donc invalidable, donc inenvoyable.
    """
    usable = usable_companies(results)
    if number < 1 or number > len(usable):
        raise ValueError(f"Entreprise {number} introuvable. Exploitables : {len(usable)}")

    payload = prepare_application(usable[number - 1], with_cv=with_cv)
    rebuild_candidatures_index(
        PROJECT / "output" / "applications",
        PROJECT / "front" / "public" / "data" / "candidatures.json",
    )
    return payload


def format_preparation(payload) -> str:
    """Compte rendu commun. L'absence d'envoi se dit à chaque fois, pas une sur deux."""
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

    lines.extend(
        [
            "",
            "Aucun envoi. Le dossier est visible dans l'onglet Spontanees du front,",
            "ou il attend une validation humaine avant de pouvoir partir.",
        ]
    )
    return "\n".join(lines)


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

    try:
        payload = prepare_numbered_application(args.number, results, with_cv=not args.no_cv)
    except ValueError as exc:
        raise SystemExit(str(exc))

    print(format_preparation(payload))


if __name__ == "__main__":
    main()
