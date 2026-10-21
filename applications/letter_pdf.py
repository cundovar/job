"""Produit le PDF de la lettre d'un dossier : ``python -m applications.letter_pdf <dossier>``.

Le serveur régénérait ce PDF en appelant directement ``lettre_to_pdf``, sans
les règles du dossier : une lettre de médiation modifiée dans l'interface
retrouvait la ligne « Portfolio » dans son bandeau. Toute production du PDF
passe maintenant par ``application_builder._write_letter_pdf``, qui lit l'offre
du dossier (``job.json``, famille de poste comprise).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .application_builder import _write_letter_pdf


def write_dossier_letter_pdf(directory: str | Path) -> Path:
    directory = Path(directory)
    letter = directory / "lettre_motivation.md"
    if not letter.is_file():
        raise FileNotFoundError(f"Aucune lettre dans {directory.name}")
    job_path = directory / "job.json"
    job = json.loads(job_path.read_text(encoding="utf-8")) if job_path.is_file() else {}
    pdf = _write_letter_pdf(letter, directory, job if isinstance(job, dict) else {})
    if pdf is None:
        raise RuntimeError(f"Export PDF de la lettre impossible pour {directory.name}")
    return pdf


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("Usage : python -m applications.letter_pdf <dossier>", file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "pdf": str(write_dossier_letter_pdf(args[0]))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
