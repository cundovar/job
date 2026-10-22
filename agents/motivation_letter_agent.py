"""
Motivation letter generation — delegated to the role-routed AI client.

Single source of truth for the writing rules: config/agent_redacteur_lettres.md
(mirror of the Hermes skill `agent-redacteur-lettres`). This module contains no
writing logic of its own.

Claude Opus is preferred, then Codex and DeepSeek are attempted in order. If no
provider can answer, this raises: there is deliberately no template fallback,
since a degraded letter that looks finished is worse than a visible error.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict

from cv_generator import rules as candidate_rules
from cv_generator.utils import period_to_text
from utils.cli_agent_bridge import CLIAgentBridgeClient

AGENT_NAME = "agent_redacteur_lettres"
PROMPT_FILE = "agent_redacteur_lettres.md"

_LOG = logging.getLogger(__name__)

# Le seul projet pédagogique citable dans les lettres de médiation.
_MEDIATION_PROJET = "Mediateur"
# Projet interdit dans ces lettres : détecté pour avertissement, jamais
# réécrit en silence (une réécriture mécanique inventerait des faits).
_PROJET_INTERDIT = "DevDoc"

#: Champs de config/criteria.yaml qui ne regardent pas l'employeur : ils ne
#: partent jamais aux fournisseurs d'IA (statut CSP, tarif, salaire visé).
_PRIVATE_PROFILE_KEYS = frozenset({"status", "tjm_cible", "salaire_cible"})


def _as_job(job: Any) -> Dict[str, Any]:
    return job if isinstance(job, dict) else {"title": str(job or "")}


def is_mediation_poste(job: Any) -> bool:
    """Vrai pour un poste de médiation : famille de l'analyse, sinon intitulé."""
    return candidate_rules.is_mediation_job(_as_job(job))


def apply_mediation_poste_rules(letter: str, job: Any) -> str:
    """Règles mécaniques des lettres médiation numérique, indépendantes de l'IA.

    - La ligne « Portfolio : … » est retirée de la signature (l'email reste ;
      mediateur.varascundo.com est cité dans le corps de la lettre).
    - Une mention de DevDoc déclenche un avertissement visible : la lettre
      n'est PAS réécrite automatiquement, c'est un signe que le prompt n'a pas
      été suivi et que la lettre doit être refaite avant envoi.
    """
    if not is_mediation_poste(job):
        return letter
    lines = letter.splitlines()
    kept = [line for line in lines if not line.strip().lower().startswith("portfolio")]
    if len(kept) != len(lines):
        _LOG.info("Ligne « Portfolio » retirée de la lettre (poste médiation numérique).")
    if _PROJET_INTERDIT in letter:
        _LOG.warning(
            "Lettre pour un poste de médiation numérique mentionnant %s : "
            "le projet à citer est %s (mediateur.varascundo.com). Regénérer la "
            "lettre avant envoi.", _PROJET_INTERDIT, _MEDIATION_PROJET,
        )
    return "\n".join(kept)

_MOIS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]

# Ligne « Ville, le … » attendue en tête de lettre : la fin peut être un
# espace réservé (« [date] ») ou une date inventée par le modèle.
_PLACE_DATE_RE = re.compile(
    r"^(?P<city>[^,\n]{1,32})?,?\s*le\s+(?P<day>\[?date\]?|\d{1,2}(?:er)?\s+\S+\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})\s*$"
)


class MotivationLetterError(RuntimeError):
    """Raised when no provider could produce a motivation letter."""


def _french_date(day: date) -> str:
    """Date en toutes lettres à la française : 18 septembre 2026, 1er mars 2026."""
    jour = "1er" if day.day == 1 else str(day.day)
    return f"{jour} {_MOIS_FR[day.month - 1]} {day.year}"


def _stamp_place_and_date(letter: str, today: date | None = None) -> str:
    """Remplace la ligne de date par la vraie date du jour.

    La date d'envoi est un fait du système : le modèle ne peut pas la
    connaître et l'invente (relevé le 18/09/2026 : « [date] », « 15 janvier
    2025 »…). On ne la demande donc pas, on la tamponne. Sans ligne
    reconnaissable en tête de lettre, on ne touche à rien.
    """
    lines = letter.splitlines()
    for index, line in enumerate(lines[:3]):
        match = _PLACE_DATE_RE.match(line.strip())
        if match:
            city = (match.group("city") or "Paris").strip()
            lines[index] = f"{city}, le {_french_date(today or date.today())}"
            return "\n".join(lines)
    return letter


def _load_system_prompt() -> str:
    prompt_path = Path(__file__).resolve().parent.parent / "config" / PROMPT_FILE
    try:
        content = prompt_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise MotivationLetterError(f"Prompt introuvable : {prompt_path}") from exc
    if not content:
        raise MotivationLetterError(f"Prompt vide : {prompt_path}")
    return (
        f"{content}\n\n"
        "## Consignes du candidat (imposees par l'appelant)\n\n"
        "Le payload peut porter `consignes_candidat` : ce que le candidat veut voir "
        "appuye dans CETTE lettre. Traite-les comme des preferences editoriales "
        "prioritaires. Elles ne peuvent jamais autoriser une experience, une "
        "competence, un chiffre ou un fait absent des preuves fournies : une consigne "
        "irrealisable se laisse de cote, elle ne s'invente pas.\n\n"
        "## Format de reponse (impose par l'appelant)\n\n"
        "Reponds UNIQUEMENT avec un objet JSON valide, sans bloc de code :\n"
        '{"lettre": "<texte complet de la lettre en markdown>", '
        '"angle_motivation": "<angle retenu en une phrase>", '
        '"consignes_suivies": ["<consigne appliquee, reformulee brievement>"], '
        '"consignes_ecartees": [{"consigne": "<consigne non appliquee>", '
        '"raison": "<pourquoi : absente des preuves, contradictoire...>"}]}\n\n'
        "Sans `consignes_candidat`, renvoie deux listes vides. Chaque consigne "
        "reçue apparait dans l'une des deux listes : une consigne ecartee se "
        "declare, elle ne disparait pas en silence."
    )


def candidate_profile(master: Dict[str, Any], variant_id: str, show_diploma_status: bool = False) -> Dict[str, Any]:
    """Extrait du profil maître pour la lettre : les faits, rien de privé.

    La lettre lisait config/criteria.yaml et les faits écrits dans son prompt,
    qui divergeaient du profil maître (périodes, expériences absentes comme
    l'accueil). Les expériences retirées et les projets interdits pour la
    variante sont écartés ; les diplômes s'affichent comme sur le CV.
    """
    person = master.get("person", {}) or {}
    positioning = master.get("positioning", {}) or {}
    forbidden = set(candidate_rules.forbidden_projects(master, variant_id))
    experiences = [
        {
            "id": exp_id,
            "organisation": item.get("organization", ""),
            "intitule": item.get("title", ""),
            "periode": period_to_text(item.get("period")),
            "faits": list(item.get("highlights", []) or []),
            "liens": list(item.get("links", []) or [])[:2],
            # Contexte de la structure (missions d'un organisme d'insertion,
            # médiation observée…) : matière à lettre, jamais un poste occupé.
            **{
                key: str(value)
                for key, value in item.items()
                if key.startswith("contexte") and isinstance(value, str) and value.strip()
            },
        }
        for exp_id, item in (master.get("experience_catalog", {}) or {}).items()
        if isinstance(item, dict) and not item.get("retired")
    ]
    projects = [
        {
            "id": project_id,
            "titre": item.get("title", ""),
            "description": item.get("description", ""),
            "liens": list(item.get("links", []) or [])[:2],
        }
        for project_id, item in (master.get("project_catalog", {}) or {}).items()
        if isinstance(item, dict) and project_id not in forbidden
    ]
    education = [
        {key: entry[key] for key in ("year", "title", "level", "school", "status") if key in entry}
        for entry in (
            candidate_rules.displayed_education_entry(item, master, variant_id, show_diploma_status)
            for item in person.get("education", []) or []
            if isinstance(item, dict)
        )
    ]
    return {
        "nom": person.get("display_name", ""),
        "email": (person.get("contact", {}) or {}).get("email", ""),
        "localisation": person.get("location", ""),
        "positionnement": (positioning.get("title_variants", {}) or {}).get(variant_id, ""),
        "accroche": (positioning.get("summary_variants", {}) or {}).get(variant_id, ""),
        "experiences": experiences,
        "projets": projects,
        "formation": education,
        "langues": person.get("languages", []),
        "formulations_interdites": list(master.get("forbidden_claims", []) or []),
    }


def _public_profile(user_profile: Dict[str, Any] | None) -> Dict[str, Any]:
    return {key: value for key, value in (user_profile or {}).items() if key not in _PRIVATE_PROFILE_KEYS}


def _build_payload(
    job: Dict[str, Any],
    recommendation: Any,
    user_profile: Dict[str, Any] | None,
    master: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    variant_id = str(getattr(recommendation, "cv_id", "") or "")
    return {
        "offre": {
            key: job.get(key)
            for key in ("title", "company", "location", "contract", "url", "description", "score", "company_type")
        },
        # Preuves de prospection mesurées (constats CONFIRMED, contacts, signaux
        # de recrutement) : la lettre y lit l'angle salarié vs freelance.
        "preuves_prospection": {
            "constats": job.get("findings") or [],
            "contact": job.get("public_contact") or [],
        },
        # Auto-description de la structure relevée par le scout (organisme de
        # formation ? agence de production ? structure sociale ?) : c'est elle
        # qui décide de l'identité d'accroche, avant tout choix rédactionnel.
        "structure": job.get("structure_profile") or {},
        # Ce que le candidat demande pour CETTE lettre : un angle à appuyer,
        # une conviction à porter. Préférence éditoriale, jamais un permis
        # d'affirmer ce que la source ne dit pas.
        "consignes_candidat": str(job.get("candidate_instructions") or "").strip()[:2000],
        "analyse_ia": job.get("ai_analysis", {}),
        "variante_cv": {
            "id": getattr(recommendation, "cv_id", ""),
            "nom": getattr(recommendation, "cv_name", ""),
            "raison": getattr(recommendation, "reason", ""),
        },
        "famille_poste": str(job.get("job_family") or ""),
        # Ce que l'annonce exige et que le profil ne couvre pas, avec ce qui
        # compense : la lettre l'aborde de front au lieu de laisser le trou.
        "ecarts": job.get("ecarts") or [],
        "profil": candidate_profile(
            master, variant_id, any(gap.get("type") == "diplome" for gap in job.get("ecarts") or [])
        ) if master else _public_profile(user_profile),
    }


def _clean_list(value: Any, limit: int = 20) -> list[str] | None:
    if not isinstance(value, list):
        return None
    return [str(item).strip()[:500] for item in value[:limit] if str(item).strip()]


def _consignes_report(consignes: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Ce que l'agent dit avoir fait des consignes du candidat.

    Trois états : ``sans_consigne`` (rien demandé), ``rapporte`` (l'agent a
    rempli les deux listes) et ``non_rapporte`` (des consignes étaient
    présentes mais l'agent n'a rien déclaré). Ce dernier cas n'est pas un
    échec : on ne sait pas, et le front doit le dire au lieu de supposer
    que tout a été suivi.
    """
    if not consignes:
        return {"etat": "sans_consigne", "suivies": [], "ecartees": []}
    suivies = _clean_list(data.get("consignes_suivies"))
    raw_ecartees = data.get("consignes_ecartees")
    ecartees = None
    if isinstance(raw_ecartees, list):
        ecartees = []
        for item in raw_ecartees[:20]:
            if isinstance(item, dict):
                consigne = str(item.get("consigne") or "").strip()[:500]
                raison = str(item.get("raison") or "").strip()[:500]
            else:
                consigne, raison = str(item).strip()[:500], ""
            if consigne:
                ecartees.append({"consigne": consigne, "raison": raison})
    if suivies is None or ecartees is None:
        return {"etat": "non_rapporte", "suivies": suivies or [], "ecartees": ecartees or []}
    return {"etat": "rapporte", "suivies": suivies, "ecartees": ecartees}


def generate_motivation_letter(
    job: Dict[str, Any],
    recommendation: Any,
    user_profile: Dict[str, Any] | None = None,
    bridge_client: CLIAgentBridgeClient | None = None,
    master: Dict[str, Any] | None = None,
) -> str:
    """Ask the CLI bridge to write the letter. Raises MotivationLetterError on failure."""
    letter, _report = generate_motivation_letter_with_report(
        job, recommendation, user_profile, bridge_client=bridge_client, master=master
    )
    return letter


def _load_master_or_none() -> Dict[str, Any] | None:
    try:
        from applications.cv_selector import load_master_profile

        return load_master_profile()
    except (OSError, ValueError):
        _LOG.warning("Profil maître illisible : la lettre part du profil de config/criteria.yaml.")
        return None


def generate_motivation_letter_with_report(
    job: Dict[str, Any],
    recommendation: Any,
    user_profile: Dict[str, Any] | None = None,
    bridge_client: CLIAgentBridgeClient | None = None,
    master: Dict[str, Any] | None = None,
) -> tuple[str, Dict[str, Any]]:
    """Comme ``generate_motivation_letter``, plus le rapport sur les consignes."""
    if master is None:
        master = _load_master_or_none()
    payload = _build_payload(job, recommendation, user_profile, master)
    system_prompt = _load_system_prompt()
    from cv_generator.ai_agents import CVAgentError, CVLLMClient

    try:
        result = CVLLMClient(bridge_client=bridge_client).complete_json(
            agent_name=AGENT_NAME,
            system_prompt=system_prompt,
            payload=payload,
        )
    except CVAgentError as exc:
        raise MotivationLetterError(str(exc)) from exc

    letter = (result.data.get("lettre") or "").strip()
    if not letter:
        raise MotivationLetterError("L'agent IA n'a pas renvoyé de lettre.")
    report = _consignes_report(payload["consignes_candidat"], result.data)
    letter = apply_mediation_poste_rules(_stamp_place_and_date(letter), job)
    return letter, report
