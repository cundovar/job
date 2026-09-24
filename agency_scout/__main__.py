"""CLI : python3 -m agency_scout {scan,add,list}

  scan  [--lat 48.85 --lng 2.39] [--rayon 3000] [--cp 75020 ...] [--ville Nanterre [--departement 92]]
        [--requete "agence web" ...] [--reanalyse] [--background]
        --cp impose le code postal de l'adresse Google : le rayon ne filtre plus (mode arrondissement).
        --ville résout la commune chez geo.api.gouv.fr : ses codes postaux deviennent le filtre
        **et** son centre devient le centre de recherche. --ville et --cp sont exclusifs.
  add   --url <site> [--nom "Nom"] [--reanalyse]   → une structure repérée à la main
        Même analyse qu'un scan, sans la découverte Places. Sans --nom, le nom est lu sur la page.
  list  [--categorie agence|formation|autre] [--min-score 0]   → JSON sur stdout
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:  # le .env racine ne remplace jamais une variable déjà posée (Docker/Coolify)
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

from tools.city_resolver import resolve_city  # noqa: E402
from agency_scout.core import (  # noqa: E402
    DEFAULT_CENTER,
    DEFAULT_RADIUS_M,
    add_agency,
    list_agencies,
    scan,
    start_background,
)

POSTAL_CODE = re.compile(r"^\d{5}$")


def resolve_perimeter(args) -> tuple[tuple[float, float], set[str] | None, str]:
    """Centre, codes postaux et libellé du périmètre demandé.

    Un code postal est cinq chiffres. « nanterre » dans ce champ ne filtrait
    rien — aucune adresse Google n'a ce code postal — et le scan rendait
    « 0 lieux » sans rien dire : c'est le silence qu'on refuse ici.
    """
    if args.ville and args.cp:
        raise ValueError("--ville et --cp sont exclusifs : choisis le périmètre par la commune ou par ses codes postaux.")
    if args.ville:
        commune = resolve_city(args.ville, args.departement)
        codes = set(commune["postal_codes"])
        if not codes:
            raise ValueError(f"{commune['label']} n'a aucun code postal publié : impossible d'en faire un périmètre.")
        if commune["latitude"] is None or commune["longitude"] is None:
            raise ValueError(f"{commune['label']} n'a pas de centre publié : impossible de centrer la recherche.")
        return (commune["latitude"], commune["longitude"]), codes, commune["label"]
    if args.cp:
        invalides = [code for code in args.cp if not POSTAL_CODE.match(code.strip())]
        if invalides:
            raise ValueError(
                f"Code postal invalide : {', '.join(invalides)}. Un code postal fait cinq chiffres "
                f"(ex. 92000) ; pour une commune, utilise --ville \"{invalides[0]}\"."
            )
        return (args.lat, args.lng), {code.strip() for code in args.cp}, args.zone_label or ""
    return (args.lat, args.lng), None, args.zone_label or ""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="agency_scout")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--lat", type=float, default=DEFAULT_CENTER[0])
    s.add_argument("--lng", type=float, default=DEFAULT_CENTER[1])
    s.add_argument("--rayon", type=int, default=DEFAULT_RADIUS_M)
    s.add_argument("--cp", action="append", help="code postal imposé, répétable (ex. --cp 75020) ; le rayon ne filtre plus")
    s.add_argument("--ville", help="commune à scanner (ex. Nanterre) ; résolue chez geo.api.gouv.fr")
    s.add_argument("--departement", help="lève l'homonymie de --ville (ex. 92)")
    s.add_argument("--requete", action="append", help="répétable ; défaut : 4 requêtes agence/formation")
    s.add_argument("--reanalyse", action="store_true", help="refaire l'IA même si le site n'a pas changé")
    s.add_argument("--background", action="store_true")
    s.add_argument("--zone-label", dest="zone_label", help="nom du périmètre, reporté dans le résumé du scan")
    a = sub.add_parser("add")
    a.add_argument("--url", required=True, help="URL du site de la structure")
    a.add_argument("--nom", help="nom affiché ; sans lui, il est lu sur la page")
    a.add_argument("--reanalyse", action="store_true", help="refaire l'analyse d'un domaine déjà connu")
    l = sub.add_parser("list")
    l.add_argument("--categorie")
    l.add_argument("--min-score", type=int, default=0)
    args = parser.parse_args(argv)

    if args.cmd == "list":
        print(json.dumps(list_agencies(args.categorie, args.min_score), ensure_ascii=False))
        return 0
    if args.cmd == "add":
        try:
            result = add_agency(args.url, args.nom, args.reanalyse)
        except Exception as exc:  # noqa: BLE001 — une URL refusée se dit, elle ne trace pas
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0
    # Périmètre résolu **avant** de lancer quoi que ce soit : une commune inconnue
    # ou homonyme doit se dire tout de suite, pas s'éteindre dans un log de fond.
    try:
        center, postal_codes, zone_label = resolve_perimeter(args)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), flush=True)
        return 1

    if args.background:
        # Le processus détaché repart sur un périmètre déjà numérique : la
        # résolution ne peut plus échouer là où personne ne la lit.
        resolved = ["scan", "--lat", str(center[0]), "--lng", str(center[1]), "--rayon", str(args.rayon)]
        for code in sorted(postal_codes or []):
            resolved += ["--cp", code]
        for requete in args.requete or []:
            resolved += ["--requete", requete]
        if args.reanalyse:
            resolved.append("--reanalyse")
        if zone_label:
            resolved += ["--zone-label", zone_label]
        print(json.dumps({**start_background(resolved), "zone_label": zone_label,
                          "postal_codes": sorted(postal_codes or [])}, ensure_ascii=False))
        return 0
    try:
        summary = scan(args.requete, center, args.rayon, args.reanalyse,
                       postal_codes=postal_codes,
                       log=lambda m: print(m, flush=True),
                       zone_label=zone_label)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), flush=True)
        return 1
    print(json.dumps({"ok": True, **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
