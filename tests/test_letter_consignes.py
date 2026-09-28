"""Consignes du candidat pour la lettre et le mail : rapport, note, régénération.

Hors-ligne : aucun appel IA, aucune lecture de data/.
"""
import json
from types import SimpleNamespace

import pytest

import applications.application_builder as builder
from agents.application_email_agent import generate_application_email
from agents.motivation_letter_agent import (
    _consignes_report,
    generate_motivation_letter_with_report,
)

RECO = SimpleNamespace(cv_id="webmaster", cv_name="CV Webmaster", reason="test")


def _bridge(data):
    class FakeBridge:
        def complete_json(self, *, agent_name, system_prompt, payload, **_):
            FakeBridge.payload = payload
            FakeBridge.system_prompt = system_prompt
            return SimpleNamespace(data=data, provider="codex_cli", model="test")
    return FakeBridge()


# ── Rapport de l'agent sur les consignes ─────────────────────────────────

def test_sans_consigne_le_rapport_le_dit():
    assert _consignes_report("", {"consignes_suivies": ["x"]})["etat"] == "sans_consigne"


def test_consigne_ecartee_se_declare_avec_sa_raison(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    job = {"title": "Webmaster", "candidate_instructions": "Parler de Kubernetes.\nTon direct."}
    bridge = _bridge({
        "lettre": "# Lettre\n\nCorps.",
        "consignes_suivies": ["Ton direct."],
        "consignes_ecartees": [{"consigne": "Parler de Kubernetes.", "raison": "absent du profil"}],
    })

    letter, report = generate_motivation_letter_with_report(job, RECO, {}, bridge_client=bridge)

    assert letter.startswith("# Lettre")
    assert report == {
        "etat": "rapporte",
        "suivies": ["Ton direct."],
        "ecartees": [{"consigne": "Parler de Kubernetes.", "raison": "absent du profil"}],
    }
    # Le format de réponse demande bien ce rapport à l'agent.
    assert "consignes_ecartees" in bridge.system_prompt


def test_rapport_absent_nest_pas_un_succes(monkeypatch):
    """Consignes données, agent muet : on ne sait pas — on ne suppose rien."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    job = {"title": "Webmaster", "candidate_instructions": "Ton direct."}
    _, report = generate_motivation_letter_with_report(
        job, RECO, {}, bridge_client=_bridge({"lettre": "# Lettre\n\nCorps."})
    )
    assert report["etat"] == "non_rapporte"


# ── Phrase perso du mail : insérée telle quelle ──────────────────────────

def test_la_phrase_perso_du_mail_est_inseree_telle_quelle():
    note = "J'ai découvert votre atelier lors des journées du patrimoine."
    email = generate_application_email(
        {"title": "Webmaster", "company": "Ville Test", "mail_personal_note": note},
        RECO,
        {"name": "Facundo Varas"},
    )
    assert f"\n{note}\n" in email
    assert email.index(note) < email.index("CV joint")


def test_sans_phrase_perso_le_mail_ne_change_pas():
    job = {"title": "Webmaster", "company": "Ville Test"}
    with_empty = generate_application_email({**job, "mail_personal_note": "  "}, RECO, {})
    assert with_empty == generate_application_email(job, RECO, {})


# ── Régénération d'un dossier existant ───────────────────────────────────

@pytest.fixture
def dossier(tmp_path):
    directory = tmp_path / "2026-09-28_ville-test_webmaster"
    directory.mkdir()
    (directory / "job.json").write_text(json.dumps({
        "title": "Webmaster", "company": "Ville Test", "description": "CMS.",
        "candidate_instructions": "Ancienne consigne.",
    }), encoding="utf-8")
    (directory / "lettre_motivation.md").write_text("Ancienne lettre", encoding="utf-8")
    (directory / "mail_candidature.md").write_text("Ancien mail", encoding="utf-8")
    (directory / "metadata.json").write_text(json.dumps({
        "job_title": "Webmaster", "company": "Ville Test",
        "status": "APPROVED", "approval_recipients_hash": "abc",
        "recommended_cv": {"cv_id": "webmaster", "cv_name": "CV Webmaster", "score": 80,
                           "matched_keywords": [], "reason": "test"},
        "files": {},
    }), encoding="utf-8")
    return directory


def test_regeneration_reecrit_lettre_mail_et_retire_lapprobation(dossier, monkeypatch):
    seen = {}

    def fake_letter(job, recommendation, user_profile=None):
        seen["job"] = job
        return "# Nouvelle lettre", {"etat": "rapporte", "suivies": ["Ton direct."], "ecartees": []}

    monkeypatch.setattr(builder, "generate_motivation_letter_with_report", fake_letter)

    result = builder.regenerate_letter_and_email(dossier, "Ton direct.", "Merci pour votre temps.")

    job = json.loads((dossier / "job.json").read_text(encoding="utf-8"))
    metadata = json.loads((dossier / "metadata.json").read_text(encoding="utf-8"))
    assert seen["job"]["candidate_instructions"] == "Ton direct."
    assert job["candidate_instructions"] == "Ton direct."
    assert job["mail_personal_note"] == "Merci pour votre temps."
    assert job["description"] == "CMS."  # la description de l'offre n'est jamais touchée
    assert (dossier / "lettre_motivation.md").read_text(encoding="utf-8") == "# Nouvelle lettre"
    assert "Merci pour votre temps." in (dossier / "mail_candidature.md").read_text(encoding="utf-8")
    assert metadata["status"] == "ready_to_apply"
    assert "approval_recipients_hash" not in metadata
    assert metadata["consignes"]["lettre"] == "Ton direct."
    assert metadata["consignes"]["rapport"]["suivies"] == ["Ton direct."]
    assert result["id"] == dossier.name


def test_consignes_videes_sont_retirees_du_dossier(dossier, monkeypatch):
    monkeypatch.setattr(
        builder, "generate_motivation_letter_with_report",
        lambda job, reco, profile=None: ("# L", {"etat": "sans_consigne", "suivies": [], "ecartees": []}),
    )
    builder.regenerate_letter_and_email(dossier, "", "")
    job = json.loads((dossier / "job.json").read_text(encoding="utf-8"))
    assert "candidate_instructions" not in job
    assert "mail_personal_note" not in job


def test_echec_de_lagent_ne_touche_a_rien(dossier, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("aucun fournisseur")

    monkeypatch.setattr(builder, "generate_motivation_letter_with_report", boom)
    with pytest.raises(RuntimeError):
        builder.regenerate_letter_and_email(dossier, "Ton direct.", "")

    assert (dossier / "lettre_motivation.md").read_text(encoding="utf-8") == "Ancienne lettre"
    assert json.loads((dossier / "job.json").read_text(encoding="utf-8"))["candidate_instructions"] == "Ancienne consigne."
    assert json.loads((dossier / "metadata.json").read_text(encoding="utf-8"))["status"] == "APPROVED"
