"""
Motivation letter generation — delegated to Hermes.

Single source of truth: the Hermes skill `agent-redacteur-lettres`.
This module contains NO writing logic. It builds the request, calls Hermes in
one-shot mode with the skill preloaded, and returns what Hermes wrote.

If Hermes cannot answer, this raises. There is deliberately no template
fallback: a degraded letter that looks finished is worse than a visible error.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any, Dict

SKILL = "agent-redacteur-lettres"
DEFAULT_TIMEOUT = 300


class MotivationLetterError(RuntimeError):
    """Raised when Hermes could not produce a motivation letter."""


def _hermes_binary() -> str:
    explicit = os.getenv("HERMES_BIN")
    if explicit:
        return explicit
    found = shutil.which("hermes")
    if found:
        return found
    fallback = os.path.expanduser("~/.local/bin/hermes")
    if os.path.exists(fallback):
        return fallback
    raise MotivationLetterError(
        "Binaire hermes introuvable (definir HERMES_BIN ou ajouter hermes au PATH)."
    )


def _build_prompt(
    job: Dict[str, Any],
    recommendation: Any,
    user_profile: Dict[str, Any] | None,
) -> str:
    payload = {
        "offre": {
            key: job.get(key)
            for key in ("title", "company", "location", "contract", "url", "description", "score")
        },
        "analyse_ia": job.get("ai_analysis", {}),
        "cv_recommande": {
            "nom": getattr(recommendation, "cv_name", ""),
            "raison": getattr(recommendation, "reason", ""),
        },
        "profil": user_profile or {},
    }
    return (
        "Redige la lettre de motivation pour l'offre ci-dessous, en appliquant "
        f"strictement la skill `{SKILL}`.\n\n"
        "Contraintes de sortie :\n"
        "- reponds UNIQUEMENT avec le texte de la lettre en markdown\n"
        "- aucun preambule, aucun commentaire, aucun bloc de code\n"
        "- n'ecris aucun fichier, le contenu est recupere sur stdout\n\n"
        "Donnees :\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
    )


def generate_motivation_letter(
    job: Dict[str, Any],
    recommendation: Any,
    user_profile: Dict[str, Any] | None = None,
) -> str:
    """Ask Hermes to write the letter. Raises MotivationLetterError on failure."""
    prompt = _build_prompt(job, recommendation, user_profile)
    timeout = int(os.getenv("HERMES_LETTER_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT)))

    env = os.environ.copy()
    env.setdefault("HERMES_HOME", "/data/hermes")

    cmd = [_hermes_binary(), "-z", prompt, "--skills", SKILL, "-t", "file"]
    model = os.getenv("HERMES_LETTER_MODEL")
    if model:
        cmd += ["-m", model]
    provider = os.getenv("HERMES_LETTER_PROVIDER")
    if provider:
        cmd += ["--provider", provider]

    try:
        result = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise MotivationLetterError(
            f"Hermes n'a pas repondu en {timeout}s pour la redaction de la lettre."
        ) from exc

    output = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    if result.returncode != 0:
        raise MotivationLetterError(
            f"Hermes a echoue (code {result.returncode}) : {stderr or output or 'aucune sortie'}"
        )
    if not output:
        raise MotivationLetterError(
            f"Hermes n'a renvoye aucun texte. stderr : {stderr or 'vide'}"
        )
    if "usage limit" in output.lower() or "API call failed" in output:
        raise MotivationLetterError(f"Hermes indisponible : {output}")

    return output
