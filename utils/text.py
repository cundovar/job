"""Normalisation de texte partagée par tout le projet.

Le même « enlever les accents et passer en minuscules » était réécrit dans
sept modules, avec de petites différences. Elles sont gardées, mais nommées :
chaque module choisit la fonction qui correspond à ce qu'il faisait.

- ``fold`` : minuscules, sans accents, espaces conservés (filtres, scoring) ;
- ``normalize`` : idem, espaces regroupés et bords nettoyés (CV, résumé) ;
- ``words`` : lettres et chiffres ASCII seulement, séparés par un espace
  (comparaison mot à mot, export du front) ;
- ``slugify`` : identifiant de dossier ou de fichier.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def strip_accents(value: Any) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", str(value or "")) if not unicodedata.combining(char)
    )


def fold(value: Any) -> str:
    """Minuscules sans accents, le reste intact. ``None`` donne une chaîne vide."""
    return strip_accents(str(value if value is not None else "").lower())


def normalize(value: Any) -> str:
    """Sans accents, minuscules, espaces regroupés."""
    return re.sub(r"\s+", " ", strip_accents(value).lower()).strip()


def words(value: Any) -> str:
    """Mots ASCII en minuscules, séparés par un espace : « Développeur Web/Mobile » → « developpeur web mobile »."""
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def slugify(value: Any, max_length: int = 80, fallback: str = "candidature") -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", strip_accents(value).lower()).strip("-")
    return (cleaned or fallback)[:max_length].strip("-")
