"""Shared fixtures: keep the suite offline.

build_application_package now delegates letter writing to the CLI bridge. Tests must not
depend on a live provider (or on Cundo's quota), so any test touching the
builder gets a stubbed letter. Tests that specifically exercise the delegation
live in test_application_agents.py and patch subprocess themselves.
"""
import pytest

from agents import motivation_letter_agent


@pytest.fixture(autouse=True)
def stub_hermes_letter(request, monkeypatch):
    if request.node.get_closest_marker("live_hermes"):
        return
    if "test_application_agents" in str(request.node.fspath):
        return
    monkeypatch.setattr(
        motivation_letter_agent,
        "generate_motivation_letter",
        lambda job, recommendation, user_profile=None, **kwargs: "# Lettre de motivation\n\nMadame, Monsieur,\n",
    )
    import applications.application_builder as builder
    # Aucune analyse IA d'annonce pendant les tests : la préparation retombe
    # sur la sélection par mots-clés, comme quand l'agent est indisponible.
    monkeypatch.setattr(builder, "analyze_offer", lambda job, master: None)
    monkeypatch.setattr(
        builder,
        "generate_motivation_letter_with_report",
        lambda job, recommendation, user_profile=None, **kwargs: (
            "# Lettre de motivation\n\nMadame, Monsieur,\n",
            {"etat": "sans_consigne", "suivies": [], "ecartees": []},
        ),
    )
