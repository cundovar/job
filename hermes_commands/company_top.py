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
    args = parser.parse_args()

    results = load_cached_companies(args.cache)
    if args.refresh or not results:
        results = run_spontaneous_search(limit=args.limit, use_ai=not args.no_ai)
    elif args.limit is not None:
        results = results[: args.limit]

    print(format_company_list(results, title=f"Prospection spontanee — {len(results)} structure(s)"))


if __name__ == "__main__":
    main()
