"""Expériences déclarées par le candidat dans ses consignes.

Règle Cundo (22/10/2026) : une consigne écrite avant la génération peut créer
une expérience absente du profil maître (« ajoute mon expérience de vendeur
chez X depuis septembre 2026 »). Elle vaut pour cette génération seulement : le
profil maître n'est pas modifié.

L'agent analyste repère ces déclarations et en donne la structure (structure,
intitulé, dates, indices des phrases). Python ne garde que ce que le texte du
candidat dit vraiment :
- la structure et l'intitulé doivent figurer mot pour mot dans les phrases
  citées (comparaison sans accents ni casse) ;
- une date n'est gardée que si son année est écrite ; un mois, que s'il est
  écrit (en chiffres ou en lettres), sinon la date entière tombe ; « en cours »
  seulement si le texte le dit ;
- les preuves (``highlights``) sont les phrases du candidat, telles quelles :
  l'agent ne rédige pas la preuve qu'il citera ensuite.

Une date que le texte ne donne pas reste inconnue : le CV part en ``review``,
jamais avec une date inventée (règle 3).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from utils.text import slugify

from .utils import normalize

MAX_DECLARED = 5
_ONGOING_RE = re.compile(r"\b(aujourd|en cours|actuellement|depuis|toujours|encore)\b")
_MONTHS = {
    "01": ("janvier", "janv"), "02": ("fevrier", "fevr"), "03": ("mars",), "04": ("avril", "avr"),
    "05": ("mai",), "06": ("juin",), "07": ("juillet", "juil"), "08": ("aout",),
    "09": ("septembre", "sept"), "10": ("octobre", "oct"), "11": ("novembre", "nov"),
    "12": ("decembre", "dec"),
}


def _statement_text(statements: List[str], indexes: List[int]) -> str:
    return " ".join(statements[index] for index in indexes)


def _date_from_text(value: Any, text: str) -> str:
    """La date proposée, réduite à ce que le texte écrit vraiment."""
    raw = str(value or "").strip()
    match = re.fullmatch(r"(\d{4})(?:-(\d{2}))?", raw)
    if not match:
        return ""
    year, month = match.group(1), match.group(2)
    if year not in text:
        return ""
    if not month:
        return year
    month_written = (
        any(re.search(rf"\b{name}\w*\b", text) for name in _MONTHS.get(month, ()))
        or re.search(rf"\b{month}\s*[/.-]\s*{year}\b", text)
        or re.search(rf"\b{int(month)}\s*[/.-]\s*{year}\b", text)
    )
    # Un mois proposé mais non écrit : la date entière tombe. La réduire à
    # l'année garderait une date que l'agent a peut-être prise ailleurs.
    return f"{year}-{month}" if month_written else ""


def validate_declared(raw: Any, master: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Expériences déclarées retenues, et ce qui a été écarté (en clair)."""
    statements = [str(item) for item in master.get("candidate_statements", []) or []]
    if not isinstance(raw, list) or not statements:
        return [], []
    catalog = master.get("experience_catalog", {}) or {}
    kept: List[Dict[str, Any]] = []
    warnings: List[str] = []
    used_ids = set(catalog)
    for item in raw[: MAX_DECLARED * 2]:
        if not isinstance(item, dict):
            continue
        indexes = sorted({
            index for index in item.get("statement_indexes") or []
            if isinstance(index, int) and 0 <= index < len(statements)
        })
        if not indexes:
            warnings.append("Expérience déclarée ignorée : aucune phrase des consignes citée.")
            continue
        text = normalize(_statement_text(statements, indexes))
        organization = " ".join(str(item.get("organization") or "").split())[:200]
        title = " ".join(str(item.get("title") or "").split())[:200]
        if organization and normalize(organization) not in text:
            warnings.append(f"Structure « {organization} » absente des consignes citées : ignorée.")
            organization = ""
        if title and normalize(title) not in text:
            warnings.append(f"Intitulé « {title} » absent des consignes citées : ignoré.")
            title = ""
        if not (organization or title):
            continue
        # Recopié de la phrase (« vendeur ») : affiché comme un intitulé.
        title = title[:1].upper() + title[1:]
        period: Dict[str, Any] = {}
        start = _date_from_text(item.get("start"), text)
        end = _date_from_text(item.get("end"), text)
        if start:
            period["start"] = start
        if end:
            period["end"] = end
        elif item.get("ongoing") is True and _ONGOING_RE.search(text):
            period["ongoing"] = True
        base = "declaree_" + slugify(organization or title, max_length=40, fallback="experience").replace("-", "_")
        identifier, suffix = base, 2
        while identifier in used_ids:
            identifier, suffix = f"{base}_{suffix}", suffix + 1
        used_ids.add(identifier)
        kept.append({
            "id": identifier,
            "proposed_id": str(item.get("id") or "")[:80],
            "organization": organization,
            "title": title,
            "period": period,
            "highlights": [statements[index] for index in indexes],
            "statement_indexes": indexes,
            "cv_role": "core",
            "source": "consignes_candidat",
        })
        if len(kept) >= MAX_DECLARED:
            break
    return kept, warnings


def declared_id_map(declared: List[Dict[str, Any]]) -> Dict[str, str]:
    """Identifiant proposé par l'agent → identifiant attribué par Python."""
    return {entry["proposed_id"]: entry["id"] for entry in declared if entry.get("proposed_id")}


def with_declared_experiences(master: Dict[str, Any], declared: Any) -> Dict[str, Any]:
    """Copie du profil où les expériences déclarées sont citables comme les autres."""
    if not isinstance(declared, list) or not declared:
        return master
    catalog = dict(master.get("experience_catalog", {}) or {})
    for entry in declared:
        if isinstance(entry, dict) and entry.get("id"):
            catalog[str(entry["id"])] = {
                key: value for key, value in entry.items() if key not in {"id", "proposed_id"}
            }
    enriched = dict(master)
    enriched["experience_catalog"] = catalog
    return enriched
