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


# ── Famille de poste : décidée une seule fois, par l'analyse de l'annonce ────

#: Familles que l'agent analyste peut attribuer à une annonce. Le CV, la lettre
#: et les règles éditoriales lisent cette valeur au lieu de deviner la nature
#: du poste chacun de leur côté (regex sur le titre, mots-clés...).
JOB_FAMILIES = (
    "developpement",
    "webmaster",
    "formation",
    "mediation_numerique",
    "mediation_sociale",
    "accueil",
    "logistique",
    "surveillance",
    "autre",
)
MEDIATION_FAMILIES = frozenset({"mediation_numerique", "mediation_sociale"})

_MEDIATION_TITLE_RE = re.compile(
    r"m[ée]diat(?:eur|rice|ion)|conseill[eè]re?s?\s+(?:num[ée]rique|emploi)|"
    r"inclusion\s+num[ée]rique|accompagnement\s+num[ée]rique|animat\w*\s+num[ée]rique",
    re.IGNORECASE,
)


def normalize_family(value: Any) -> str:
    family = normalize(value).replace(" ", "_")
    return family if family in JOB_FAMILIES else "autre"


def is_mediation_job(job: Dict[str, Any]) -> bool:
    """Vrai pour un poste de médiation (numérique ou sociale).

    La famille attribuée par l'analyse de l'annonce fait foi. Sans elle
    (annonce jamais analysée, analyse en échec), on retombe sur l'intitulé.
    """
    family = str((job or {}).get("job_family") or "")
    if family in JOB_FAMILIES and family != "autre":
        return family in MEDIATION_FAMILIES
    return bool(_MEDIATION_TITLE_RE.search(str((job or {}).get("title") or "")))


# Liens retirés du CV, quelle que soit la variante (décision Cundo 22/10/2026) :
# docdevdoc.varascundo.com ne doit plus jamais apparaître ; la documentation de
# DevDoc vit désormais sous https://devdoc.varascundo.com/docs/.
RETIRED_LINK_HOSTS = frozenset({"docdevdoc.varascundo.com"})


def is_retired_link(url: Any) -> bool:
    from urllib.parse import urlparse

    raw = str(url or "").strip()
    host = (urlparse(raw).netloc or raw.split("/")[0]).lower().removeprefix("www.")
    return host in RETIRED_LINK_HOSTS


def shown_links(links: Any) -> List[str]:
    """Les liens d'une entrée du CV, sans les liens retirés ni doublons."""
    kept: List[str] = []
    for link in links or []:
        if link and not is_retired_link(link) and link not in kept:
            kept.append(str(link))
    return kept
