from types import SimpleNamespace

import pytest

from agents import (
    MotivationLetterError,
    generate_application_email,
    generate_motivation_letter,
)
from agents import motivation_letter_agent
from utils.cli_agent_bridge import CLIBridgeError
from applications import recommend_cv


def test_generate_motivation_letter_delegates_to_bridge():
    """La redaction passe par le bridge CLI : on verifie l'appel, pas le texte."""
    job = {
        "title": "Webmaster institutionnel WordPress",
        "company": "Ville Test",
        "description": "CMS WordPress, accessibilite RGAA, documentation.",
        "score": 86,
    }
    recommendation = recommend_cv(job)
    captured = {}

    class FakeBridge:
        def complete_json(
            self,
            *,
            agent_name,
            system_prompt,
            payload,
            preferred_provider=None,
            preferred_model=None,
            reasoning_effort=None,
        ):
            captured["agent_name"] = agent_name
            captured["system_prompt"] = system_prompt
            captured["payload"] = payload
            captured["provider"] = preferred_provider
            captured["model"] = preferred_model
            return SimpleNamespace(
                data={"lettre": "# Lettre\n\nMadame, Monsieur,"},
                provider="codex_cli",
                model="test",
            )

    letter = generate_motivation_letter(
        job, recommendation, {"name": "Facundo Varas"}, bridge_client=FakeBridge()
    )

    assert letter.startswith("# Lettre")
    assert captured["agent_name"] == "agent_redacteur_lettres"
    assert captured["provider"] == "claude"
    assert captured["model"] == "opus"
    assert "Ville Test" in str(captured["payload"])
    assert "lettre" in captured["system_prompt"]


def test_generate_motivation_letter_falls_back_then_raises():
    """Essaie Opus puis Codex, et remonte l'erreur — jamais de lettre degradee."""
    job = {"title": "Dev", "company": "X", "description": ""}
    recommendation = recommend_cv(job)
    tried = []

    class DeadBridge:
        def complete_json(
            self,
            *,
            agent_name,
            system_prompt,
            payload,
            preferred_provider=None,
            preferred_model=None,
            reasoning_effort=None,
        ):
            tried.append(preferred_provider)
            raise CLIBridgeError("bridge indisponible")

    with pytest.raises(MotivationLetterError):
        generate_motivation_letter(job, recommendation, {}, bridge_client=DeadBridge())

    assert tried == ["claude", "codex"]


def test_generate_application_email_mentions_cv_to_attach():
    job = {
        "title": "Administrateur applicatif",
        "company": "Association Exemple",
        "description": "Support applicatif, SQL, ERP et documentation.",
    }
    recommendation = recommend_cv(job)

    email = generate_application_email(job, recommendation, {"name": "Facundo Varas (Cundo)"})

    assert "Candidature" in email and "Administrateur applicatif" in email
    assert "Association Exemple" in email
    assert recommendation.cv_name in email
    assert "Facundo Varas" in email
