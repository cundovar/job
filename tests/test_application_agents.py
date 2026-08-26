from types import SimpleNamespace

import pytest

from agents import (
    MotivationLetterError,
    generate_application_email,
    generate_motivation_letter,
)
from agents import motivation_letter_agent
from applications import recommend_cv


def test_generate_motivation_letter_delegates_to_hermes(monkeypatch):
    """La redaction est deleguee a Hermes : on verifie l'appel, pas le texte."""
    job = {
        "title": "Webmaster institutionnel WordPress",
        "company": "Ville Test",
        "description": "CMS WordPress, accessibilite RGAA, documentation et service public.",
        "score": 86,
        "ai_analysis": {"angle_motivation": "Insister sur CMS, qualite web et support utilisateurs."},
    }
    recommendation = recommend_cv(job)
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout="# Lettre\n\nMadame, Monsieur,", stderr="")

    monkeypatch.setattr(motivation_letter_agent.subprocess, "run", fake_run)
    monkeypatch.setattr(motivation_letter_agent, "_hermes_binary", lambda: "/usr/bin/hermes")

    letter = generate_motivation_letter(job, recommendation, {"name": "Facundo Varas"})

    assert letter.startswith("# Lettre")
    assert "--skills" in captured["cmd"]
    assert "agent-redacteur-lettres" in captured["cmd"]
    assert "Ville Test" in captured["cmd"][2]  # le prompt porte les donnees de l'offre


def test_generate_motivation_letter_raises_instead_of_degrading(monkeypatch):
    """Aucun fallback template : un echec Hermes doit remonter."""
    job = {"title": "Dev", "company": "X", "description": ""}
    recommendation = recommend_cv(job)

    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="HTTP 429: usage limit reached")

    monkeypatch.setattr(motivation_letter_agent.subprocess, "run", fake_run)
    monkeypatch.setattr(motivation_letter_agent, "_hermes_binary", lambda: "/usr/bin/hermes")

    with pytest.raises(MotivationLetterError):
        generate_motivation_letter(job, recommendation, {})


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
