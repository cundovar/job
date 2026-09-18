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


def test_generate_motivation_letter_delegates_to_bridge(monkeypatch):
    """La redaction passe par le bridge CLI : on verifie l'appel, pas le texte."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
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


def test_generate_motivation_letter_falls_back_then_raises(monkeypatch):
    """Essaie Opus puis Codex, et remonte l'erreur — jamais de lettre degradee."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
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


def test_french_date_formats_day_month_year():
    from datetime import date

    formater = motivation_letter_agent._french_date

    assert formater(date(2026, 9, 18)) == "18 septembre 2026"
    assert formater(date(2025, 1, 15)) == "15 janvier 2025"
    assert formater(date(2026, 3, 1)) == "1er mars 2026"


def test_letter_date_is_stamped_not_invented(monkeypatch):
    """La date du jour est un fait du système : le modèle ne peut pas la connaître.

    Relevé du 18/09/2026 sur les quatre dossiers spontanés : « [date] » en
    clair, « 15 janvier 2025 », « 12 juin 2025 », « 5 février 2026 » — quatre
    lettres, quatre dates, aucune juste.
    """
    from datetime import date

    stamp = motivation_letter_agent._stamp_place_and_date
    today = date(2026, 9, 18)

    # Les trois formes observées : espace réservé, date inventée, sans ville.
    assert stamp("Paris, le [date]\n\nMadame, Monsieur,", today) == (
        "Paris, le 18 septembre 2026\n\nMadame, Monsieur,"
    )
    assert stamp("Paris, le 15 janvier 2025\n\nMadame, Monsieur,", today).startswith(
        "Paris, le 18 septembre 2026"
    )
    assert stamp("Lyon, le 12 juin 2025\n\nMadame, Monsieur,", today).startswith(
        "Lyon, le 18 septembre 2026"
    )

    # Sans ligne de date reconnaissable, on ne touche à rien.
    intact = "Madame, Monsieur,\n\nJe vous écris au sujet de votre annonce."
    assert stamp(intact, today) == intact


def test_generated_letter_carries_the_real_date(monkeypatch):
    """Le tampon de date s'applique à la sortie réelle de l'agent."""
    from datetime import date

    class PlaceholderBridge:
        def complete_json(self, **kwargs):
            return SimpleNamespace(
                data={"lettre": "Paris, le [date]\n\nMadame, Monsieur,\n\nVoici mon parcours."},
                provider="codex_cli",
                model="test",
            )

    job = {"title": "Dev", "company": "X", "description": ""}
    letter = generate_motivation_letter(job, recommend_cv(job), {}, bridge_client=PlaceholderBridge())

    assert "[date]" not in letter
    assert letter.startswith("Paris, le ")
    assert str(date.today().year) in letter.splitlines()[0]


def test_spontaneous_email_never_mentions_a_posting():
    """Aucune annonce n'existe sur la voie spontanée : pas de « le poste de »."""
    job = {
        "title": "Développeur web / Intégrateur",
        "company": "Agence Test",
        "description": "Candidature spontanée.",
        "source": "prospection_spontanee",
    }
    recommendation = recommend_cv(job)

    email = generate_application_email(job, recommendation, {"name": "Facundo Varas"})

    assert "Candidature spontanée" in email
    assert "candidature spontanée en tant que Développeur web / Intégrateur" in email
    assert "le poste de" not in email


def test_job_ad_email_keeps_the_posting_wording():
    """Sur la voie annonce, le poste existe : la formule initiale reste."""
    job = {
        "title": "Développeur Symfony",
        "company": "Entreprise Annonce",
        "description": "Offre publiée en ligne.",
        "source": "welcometothejungle",
    }
    recommendation = recommend_cv(job)

    email = generate_application_email(job, recommendation, {"name": "Facundo Varas"})

    assert "pour le poste de Développeur Symfony" in email
    assert "spontanée" not in email
