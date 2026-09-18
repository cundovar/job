"""Prospecteur lisant le banc d'essai tenu à la main dans config/companies.csv.

Le CSV est la seule entrée du pipeline : une entreprise n'y figure que si son
URL a été relevée en clair. Les pistes sans URL restent dans companies.yaml,
qui est l'espace de qualification humaine.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List

from .base_prospector import EXCLUDED_STATUSES, BaseProspector

DEFAULT_CSV_PATH = Path(__file__).resolve().parent.parent / "config" / "companies.csv"
REQUIRED_COLUMNS = ("nom", "site")


class CSVProspector(BaseProspector):
    def __init__(self, path: str | Path = DEFAULT_CSV_PATH) -> None:
        self._path = Path(path)

    def find(self, criteria: Dict[str, Any]) -> List[Dict]:
        if not self._path.exists():
            raise FileNotFoundError(
                f"Banc d'essai introuvable : {self._path}. "
                "Les entreprises et leurs URLs sont fournies à la main, jamais inventées."
            )

        with self._path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = [column for column in REQUIRED_COLUMNS if column not in (reader.fieldnames or [])]
            if missing:
                raise ValueError(
                    f"Colonnes manquantes dans {self._path} : {', '.join(missing)}"
                )
            rows = [self._clean_row(row) for row in reader]

        companies: List[Dict] = []
        for row in rows:
            if not row.get("nom") or not row.get("site"):
                # Une ligne sans URL ne peut produire aucune mesure : on la saute
                # plutôt que de compléter l'URL nous-mêmes.
                continue
            if row.get("statut") in EXCLUDED_STATUSES:
                continue
            companies.append(row)
        return companies

    @staticmethod
    def _clean_row(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            key: (value.strip() if isinstance(value, str) else value)
            for key, value in row.items()
            if key is not None
        }
