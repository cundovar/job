"""Shared fixtures: keep the suite offline.

build_application_package now delegates letter writing to Hermes. Tests must not
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
        lambda job, recommendation, user_profile=None: "# Lettre de motivation\n\nMadame, Monsieur,\n",
    )
    import applications.application_builder as builder
    monkeypatch.setattr(
        builder,
        "generate_motivation_letter",
        lambda job, recommendation, user_profile=None: "# Lettre de motivation\n\nMadame, Monsieur,\n",
    )
