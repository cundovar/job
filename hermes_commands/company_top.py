from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from company_analysis.verifier import CONFIRMED
from pipeline_spontaneous import CACHE_PATH, run_spontaneous_search


def load_cached_companies(path: str | Path = CACHE_PATH) -> List[Dict[str, Any]]:
    cache_path = Path(path)
    if not cache_path.exists():
        return []
    try:
        loaded = json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return loaded if isinstance(loaded, list) else []


def _format_address(opportunity: Dict[str, Any]) -> str:
    """Recompose l'adresse à partir de ce qui est réellement présent.

    Aucun champ n'est déduit d'un autre : une ville sans numéro de rue reste une
    ville, et un code postal absent ne se devine pas depuis l'arrondissement.
    """
    parts = [
        str(opportunity.get(key) or "").strip()
        for key in ("address", "postal_code", "location")
    ]
    street, postal, city = parts
    if postal and city.replace(" ", "").endswith(postal):
        # "Paris 75020" contient déjà le code postal : ne pas le répéter.
        postal = ""
    return ", ".join(part for part in (street, " ".join(p for p in (postal, city) if p)) if part)


def format_company_list(results: List[Dict[str, Any]], title: str) -> str:
    if not results:
        return f"{title}\n\nAucune entreprise analysee."

    lines = [title, ""]
    usable = 0
    for result in results:
        opportunity = result.get("opportunity")
        confirmed = [
            claim for claim in result.get("claims", []) if claim.get("status") == CONFIRMED
        ]
        if opportunity:
            usable += 1
            lines.append(f"{usable}. {result.get('company', 'Structure non renseignee')}")
            lines.append(f"   Poste vise : {opportunity.get('title', 'Non renseigne')}")
            lines.append(f"   URL : {result.get('url', 'Non renseignee')}")
            # Sans cette ligne l'adresse existait dans le CSV mais n'apparaissait
            # nulle part : un agent en concluait qu'aucune adresse n'était connue,
            # puis en inventait. On affiche ce qu'on a, et rien quand on n'a rien.
            lines.append(f"   Adresse : {_format_address(opportunity) or 'Non renseignee'}")
            lines.append(f"   Constats confirmes : {len(confirmed)}")
            for claim in confirmed:
                lines.append(f"   - {claim['claim']}")
        else:
            lines.append(f"-. {result.get('company', 'Structure non renseignee')} : REFUS")
            lines.append(f"   Motif : {result.get('refusal', 'non renseigne')}")
        lines.append("")

    lines.append(f"Exploitables : {usable} / {len(results)}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Affiche les entreprises ciblees et leurs constats verifies."
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--cache", default=str(CACHE_PATH))
    parser.add_argument(
        "--refresh", action="store_true", help="Relance les mesures au lieu de lire le cache."
    )
    parser.add_argument("--no-ai", action="store_true")
    parser.add_argument(
        "--code-postal",
        default=None,
        help="Ne garder que les entreprises de cette zone (ex. 75020, ou 75 pour Paris)",
    )
    args = parser.parse_args()

    results = load_cached_companies(args.cache)
    if args.refresh or not results or args.code_postal:
        # Une demande zonée repasse toujours par le banc d'essai : le cache ne
        # sait pas de quelle zone il vient, le filtrer donnerait une réponse
        # plausible mais non vérifiée.
        results = run_spontaneous_search(
            limit=args.limit, use_ai=not args.no_ai, postal_code=args.code_postal
        )
    elif args.limit is not None:
        results = results[: args.limit]

    print(format_company_list(results, title=f"Prospection spontanee — {len(results)} structure(s)"))


if __name__ == "__main__":
    main()
