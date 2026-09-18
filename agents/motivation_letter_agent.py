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
        "## Format de reponse (impose par l'appelant)\n\n"
        "Reponds UNIQUEMENT avec un objet JSON valide, sans bloc de code :\n"
        '{"lettre": "<texte complet de la lettre en markdown>", '
        '"angle_motivation": "<angle retenu en une phrase>"}'
    )


def _build_payload(
    job: Dict[str, Any],
    recommendation: Any,
    user_profile: Dict[str, Any] | None,
) -> Dict[str, Any]:
    return {
        "offre": {
            key: job.get(key)
            for key in ("title", "company", "location", "contract", "url", "description", "score")
        },
        "analyse_ia": job.get("ai_analysis", {}),
        "variante_cv": {
            "id": getattr(recommendation, "cv_id", ""),
            "nom": getattr(recommendation, "cv_name", ""),
            "raison": getattr(recommendation, "reason", ""),
        },
        "profil": user_profile or {},
    }


def generate_motivation_letter(
    job: Dict[str, Any],
    recommendation: Any,
    user_profile: Dict[str, Any] | None = None,
    bridge_client: CLIAgentBridgeClient | None = None,
) -> str:
    """Ask the CLI bridge to write the letter. Raises MotivationLetterError on failure."""
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
    return _stamp_place_and_date(letter)
