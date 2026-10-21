"""Règles éditoriales du candidat, lues dans le profil maître.

Une règle décidée par le candidat (masquer la VAE, diplômes obligatoires,
projet interdit sur une famille de CV, expériences obligatoires) se déclare
une seule fois dans ``data/cv_master_profile.json`` et se lit ici. Prompts,
assemblage, validateur et lettre passent par ce module : une règle écrite
seulement dans un prompt reste une suggestion au modèle, et c'est ce qui
laissait passer « VAE en cours » ou DevDoc malgré les décisions du candidat.

Clés lues :
- ``layout_constraints.hide_vae_status_variants`` : variantes sans statut de diplôme ;
- ``layout_constraints.required_education_by_variant`` : diplômes à afficher ;
- ``layout_constraints.required_experiences_by_variant`` : ``"*"`` = valeur par défaut ;
- ``adaptation_rules.forbidden_projects_by_variant`` : projets jamais affichés ;
- ``adaptation_rules.standing_experience_preferences_by_variant`` : préférences permanentes.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .utils import normalize

#: Paragraphe commun aux prompts des agents CV : la place des consignes du
#: candidat dans la hiérarchie des sources. Une seule rédaction, partagée.
CANDIDATE_INSTRUCTIONS_CLAUSE = (
    "Les consignes_candidat sont écrites par le candidat lui-même : elles sont la source de "
    "vérité la plus haute, au-dessus du profil maître. Toute information qu'elles affirment "
    "(expérience, mission, outil, compétence, intitulé, date, résultat) est vraie et utilisable "
    "même sans preuve dans le profil ; toute consigne de présentation (retirer, regrouper, "
    "renommer, réordonner) s'applique. En cas de contradiction avec le profil maître, la "
    "consigne l'emporte. Une puce qui s'appuie sur une consigne cite la source "
    "« consignes_candidat:N », N étant l'indice de la déclaration dans declarations_candidat."
)


def _layout(master: Dict[str, Any]) -> Dict[str, Any]:
    return (master or {}).get("layout_constraints", {}) or {}


def _adaptation(master: Dict[str, Any]) -> Dict[str, Any]:
    return (master or {}).get("adaptation_rules", {}) or {}


def _by_variant(rules: Any, variant_id: str, default: Any) -> Any:
    if not isinstance(rules, dict):
        return default
    return rules.get(variant_id, rules.get("*", default))


def hides_diploma_status(master: Dict[str, Any], variant_id: str) -> bool:
    """Vrai si la variante n'affiche aucun statut de diplôme (« VAE en cours »)."""
    return variant_id in (_layout(master).get("hide_vae_status_variants") or [])


def displayed_education_entry(entry: Dict[str, Any], master: Dict[str, Any], variant_id: str) -> Dict[str, Any]:
    """Le diplôme tel qu'il s'affiche pour la variante : sans statut si la règle le demande.

    Ce n'est pas un choix éditorial réécrit : l'agent choisit le diplôme, la
    façon de l'afficher est une décision du candidat portée par le profil.
    """
    if not hides_diploma_status(master, variant_id):
        return entry
    return {key: value for key, value in entry.items() if key != "status"}


def required_education(master: Dict[str, Any], variant_id: str) -> List[str]:
    value = _by_variant(_layout(master).get("required_education_by_variant"), variant_id, [])
    return [str(item) for item in value] if isinstance(value, list) else []


def required_experiences(master: Dict[str, Any], variant_id: str) -> List[Any]:
    """Expériences obligatoires de la variante (``"*"`` = valeur par défaut).

    Chaque entrée est un identifiant, ou une liste d'alternatives dont une seule suffit.
    Une variante déclarée avec ``[]`` n'en impose aucune.
    """
    value = _by_variant(_layout(master).get("required_experiences_by_variant"), variant_id, [])
    return value if isinstance(value, list) else []


def forbidden_projects(master: Dict[str, Any], variant_id: str) -> List[str]:
    value = _by_variant(_adaptation(master).get("forbidden_projects_by_variant"), variant_id, [])
    return [str(item) for item in value] if isinstance(value, list) else []


def standing_preferences(master: Dict[str, Any]) -> Dict[str, List[str]]:
    value = _adaptation(master).get("standing_experience_preferences_by_variant") or {}
    return {
        str(variant): [str(item) for item in items]
        for variant, items in value.items()
        if isinstance(items, list) and items
    } if isinstance(value, dict) else {}


# ── Consignes du candidat : demander le retrait d'une expérience ─────────────

_REMOVAL_VERB = r"(?:retir\w*|enl[eè]v\w*|supprim\w*|masqu\w*|cach\w*|ne mets? pas|pas de|pas d'|sans)"
#: Mots qui peuvent séparer le verbe du nom : « retire l'expérience chez X ».
_FILLER = r"(?:(?:l'|l’|le|la|les|de|du|des|d'|d’|mon|ma|mes|mention|experience|mission|bloc|chez|poste)\s*)*"


def experience_names(master: Dict[str, Any], experience_id: str) -> List[str]:
    """Les noms par lesquels le candidat peut désigner une expérience.

    Identifiant lisible, organisation complète, et organisation sans son
    complément (« Le Petit Studio » pour « Le Petit Studio & Associés »).
    """
    item = ((master or {}).get("experience_catalog", {}) or {}).get(experience_id) or {}
    organization = normalize(item.get("organization"))
    names = {normalize(experience_id.replace("_", " ")), organization}
    head = re.split(r"\s*(?:&|·|\(|\s-\s|,)\s*", organization)[0].strip()
    names.add(head)
    return sorted((name for name in names if len(name) > 2), key=len, reverse=True)


def statement_removes(statement: str, names: List[str]) -> bool:
    """Vrai si la déclaration demande de retirer l'un de ces noms.

    Le verbe de retrait doit porter sur le nom lui-même : « mettre en avant X,
    sans cacher la formation » ne retire pas X.
    """
    text = normalize(statement)
    for name in names:
        pattern = rf"{_REMOVAL_VERB}\s+{_FILLER}{re.escape(name)}\b"
        if re.search(pattern, text):
            return True
    return False
