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

import re
from datetime import date
from pathlib import Path
from typing import Any, Dict

from utils.cli_agent_bridge import CLIAgentBridgeClient

AGENT_NAME = "agent_redacteur_lettres"
PROMPT_FILE = "agent_redacteur_lettres.md"

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


def _build_payload(
    job: Dict[str, Any],
    recommendation: Any,
    user_profile: Dict[str, Any] | None,
) -> Dict[str, Any]:
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
        "profil": user_profile or {},
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
) -> str:
    """Ask the CLI bridge to write the letter. Raises MotivationLetterError on failure."""
    letter, _report = generate_motivation_letter_with_report(
        job, recommendation, user_profile, bridge_client=bridge_client
    )
    return letter


def generate_motivation_letter_with_report(
    job: Dict[str, Any],
    recommendation: Any,
    user_profile: Dict[str, Any] | None = None,
    bridge_client: CLIAgentBridgeClient | None = None,
) -> tuple[str, Dict[str, Any]]:
    """Comme ``generate_motivation_letter``, plus le rapport sur les consignes."""
    payload = _build_payload(job, recommendation, user_profile)
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
    return _stamp_place_and_date(letter), report
