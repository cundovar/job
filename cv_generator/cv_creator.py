"""Le squelette non éditorial d'un CV.

Ce module ne choisit plus ni expérience, ni projet, ni formation, ni compétence,
et ne regroupe plus rien : ces décisions appartiennent aux agents IA. Il ne
fournit que ce qui n'est pas un choix — le bloc identité, les langues et les
contraintes de gabarit que l'agent rédacteur doit respecter.
"""

from __future__ import annotations

from typing import Any, Dict, List


def _contact_for_variant(person: Dict[str, Any], master: Dict[str, Any], variant_id: str) -> Dict[str, Any]:
    """Restreint les coordonnées affichées selon la variante.

    Ce n'est pas un choix éditorial mais une règle de confidentialité du profil
    maître : une candidature d'accueil n'expose pas le dépôt GitHub.
    """
    contact = person.get("contact", {})
    allowed_fields = (
        master.get("adaptation_rules", {})
        .get("contact_fields_by_variant", {})
        .get(variant_id)
    )
    if not isinstance(allowed_fields, list):
        return contact
    return {
        field: contact[field]
        for field in allowed_fields
        if field in contact and contact[field]
    }


def build_structural_shell(master: Dict[str, Any], variant_id: str) -> Dict[str, Any]:
    """Ce que l'agent rédacteur reçoit sans avoir à le décider.

    Aucune expérience, aucun projet, aucune compétence : uniquement l'identité,
    les langues et les limites de mise en page à respecter.
    """
    person = master.get("person", {})
    return {
        "contact": _contact_for_variant(person, master, variant_id),
        "location": person.get("location", ""),
        "languages": person.get("languages", []),
        "layout_constraints": master.get("layout_constraints", {}),
    }


def available_education_titles(master: Dict[str, Any]) -> List[str]:
    """Intitulés exacts que l'agent peut reprendre, sans présélection."""
    return [
        str(item.get("title"))
        for item in master.get("person", {}).get("education", [])
        if isinstance(item, dict) and item.get("title")
    ]
