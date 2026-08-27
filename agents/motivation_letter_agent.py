"""
Motivation letter generation — delegated to the subscription CLI bridge.

Single source of truth for the writing rules: config/agent_redacteur_lettres.md
(mirror of the Hermes skill `agent-redacteur-lettres`). This module contains no
writing logic of its own.

The bridge is used rather than the `hermes` binary because it is reachable from
both the local environment and the Coolify container (data/ is bind-mounted, so
the socket is shared). If the bridge cannot answer, this raises: there is
deliberately no template fallback, since a degraded letter that looks finished
is worse than a visible error.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from utils.cli_agent_bridge import CLIAgentBridgeClient

AGENT_NAME = "agent_redacteur_lettres"
PROMPT_FILE = "agent_redacteur_lettres.md"


class MotivationLetterError(RuntimeError):
    """Raised when no provider could produce a motivation letter."""


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
    return letter
