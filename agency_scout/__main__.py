"""CLI : python3 -m agency_scout {scan,list}

  scan  [--lat 48.85 --lng 2.39] [--rayon 3000] [--requete "agence web" ...] [--reanalyse] [--background]
  list  [--categorie agence|formation|autre] [--min-score 0]   → JSON sur stdout
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:  # le .env racine ne remplace jamais une variable déjà posée (Docker/Coolify)
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

from agency_scout.core import DEFAULT_CENTER, DEFAULT_RADIUS_M, list_agencies, scan, start_background  # noqa: E402

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="agency_scout")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--lat", type=float, default=DEFAULT_CENTER[0])
    s.add_argument("--lng", type=float, default=DEFAULT_CENTER[1])
    s.add_argument("--rayon", type=int, default=DEFAULT_RADIUS_M)
    s.add_argument("--requete", action="append", help="répétable ; défaut : 4 requêtes agence/formation")
    s.add_argument("--reanalyse", action="store_true", help="refaire l'IA même si le site n'a pas changé")
    s.add_argument("--background", action="store_true")
    l = sub.add_parser("list")
    l.add_argument("--categorie")
    l.add_argument("--min-score", type=int, default=0)
    args = parser.parse_args(argv)

    if args.cmd == "list":
        print(json.dumps(list_agencies(args.categorie, args.min_score), ensure_ascii=False))
        return 0
    if args.background:
        print(json.dumps(start_background([a for a in argv if a != "--background"])))
        return 0
    try:
        summary = scan(args.requete, (args.lat, args.lng), args.rayon, args.reanalyse,
                       log=lambda m: print(m, flush=True))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), flush=True)
        return 1
    print(json.dumps({"ok": True, **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
