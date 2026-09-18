"""Interface commune des prospecteurs d'entreprises.

Miroir de scrapers/base_scraper.py : là où un scraper part de mots-clés pour
trouver des annonces, un prospecteur part de critères de ciblage pour trouver
des entreprises qui, elles, ne publient rien.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List

import yaml

DEFAULT_CRITERIA_PATH = Path(__file__).resolve().parent.parent / "config" / "companies.yaml"

# Statuts de qualification posés à la main dans companies.yaml / companies.csv.
KNOWN_STATUSES = {"a_qualifier", "prioritaire", "secondaire", "ecartee"}
EXCLUDED_STATUSES = {"ecartee"}


def load_targeting_criteria(path: str | Path = DEFAULT_CRITERIA_PATH) -> Dict[str, Any]:
    """Charge les critères de ciblage. Absents, ils ne sont pas devinés."""
    criteria_path = Path(path)
    if not criteria_path.exists():
        raise FileNotFoundError(
            f"Critères de ciblage introuvables : {criteria_path}. "
            "Ce fichier est un choix produit, il ne doit pas être généré automatiquement."
        )
    loaded = yaml.safe_load(criteria_path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Critères de ciblage invalides : {criteria_path}")
    return loaded


def target_title_for(company: Dict[str, Any], criteria: Dict[str, Any]) -> str:
    """Intitulé de poste visé pour une entreprise.

    Ce n'est pas un constat sur l'entreprise mais notre intention de
    candidature : il vient de la configuration, jamais du site.
    """
    override = str(company.get("poste_vise") or "").strip()
    if override:
        return override
    mapping = criteria.get("poste_vise_par_type")
    mapping = mapping if isinstance(mapping, dict) else {}
    company_type = str(company.get("type") or "").strip()
    return str(mapping.get(company_type) or "").strip()


class BaseProspector(ABC):
    @abstractmethod
    def find(self, criteria: Dict[str, Any]) -> List[Dict]:
        """Retourne les entreprises ciblées, sans jugement ni mesure."""
        raise NotImplementedError
