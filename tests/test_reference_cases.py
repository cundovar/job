"""Cas de référence du refactor de la chaîne CV et lettre (étape 1 du plan).

Chaque test décrit un comportement attendu, vérifié en Python, sans appel IA.
Les défauts connus au 21/10/2026 sont marqués ``xfail(strict=True)`` avec
l'étape du plan qui doit les corriger : le test échoue aujourd'hui comme
prévu, et la suite devient rouge dès qu'une correction le fait passer sans
qu'on retire la marque — on sait ainsi exactement quand chaque défaut tombe.

Le profil maître est fictif (dérivé de tests/fixtures/cv_master_sample.json) :
aucune donnée de data/ n'est recopiée ici (règle n° 1 de CLAUDE.md).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict

import pytest

from agents.motivation_letter_agent import is_mediation_poste
from cv_generator import ai_agents
from cv_generator.ai_agents import ANALYZER_PROMPT, AgentResult, _assemble_cv_content
from cv_generator.cv_truth_validator import (
    candidate_excludes,
    validate_cv_content,
    with_candidate_statements,
)

FIXTURES = Path(__file__).parent / "fixtures"
CDA = "Titre professionnel Concepteur (fictif)"
CAP = "CAP Petite enfance (fictif)"
RUN = AgentResult({}, "injected", "test")


def _todo(step: str, reason: str):
    return pytest.mark.xfail(strict=True, reason=f"Étape {step} du plan : {reason}")


@pytest.fixture
def master() -> Dict[str, Any]:
    """Profil fictif complété des règles que le vrai profil maître déclare."""
    base = json.loads((FIXTURES / "cv_master_sample.json").read_text(encoding="utf-8"))
    m = copy.deepcopy(base)
    m["person"]["education"] = [
        {"year": 2026, "title": CDA, "level": "niveau 6", "status": "VAE en cours"},
        {"year": 2019, "title": "Titre professionnel Developpeur web (fictif)", "level": "Bac+2"},
        {"year": 2012, "title": CAP},
    ]
    for variant_id in ("mediation_numerique", "mediation_sociale"):
        m["cv_variants"].append(
            {"id": variant_id, "title": variant_id, "profile": "Profil fictif.", "tags": ["mediation"]}
        )
    m["project_catalog"]["projet_documentation"] = {
        "year": 2024,
        "title": "Plateforme de documentation (fictive)",
        "description": "Projet de documentation technique invente.",
        "technologies": ["Vue.js"],
    }
    m["experience_catalog"]["studio_fictif"]["organization"] = "Le Petit Studio & Associés"
    lc = m["layout_constraints"]
    lc["max_education_items"] = 3
    lc["max_projects"] = 2
    lc["hide_vae_status_variants"] = ["mediation_numerique", "mediation_sociale"]
    lc["required_education_by_variant"] = {"mediation_numerique": [CAP]}
    lc["required_experiences_by_variant"] = {"*": ["agence_exemple"], "mediation_sociale": []}
    m["adaptation_rules"]["forbidden_projects_by_variant"] = {
        "mediation_numerique": ["projet_documentation"],
        "mediation_sociale": ["projet_documentation"],
    }
    return m


def _assemble(master, variant, *, education=None, projects=None):
    proposed = {
        "title": "Titre",
        "profile": "Accroche fictive.",
        "skills": [],
        "experiences": [
            {"id": "agence_exemple", "bullets": [{"text": "Puce.", "sources": ["agence_exemple:0"]}]}
        ],
        "projects": projects or [],
        "education": education if education is not None else [CDA],
    }
    plan = {"selected_base_variant": variant}
    return _assemble_cv_content(proposed, {"title": "Poste"}, master, plan, RUN, "test"), plan


def _codes(content, master, plan):
    return {issue["code"] for issue in validate_cv_content(content, master, plan)["issues"]}


# ── Étape 2 : règles éditoriales appliquées en Python ────────────────────────

def test_la_mention_vae_est_masquee_pour_une_variante_mediation(master):
    content, _ = _assemble(master, "mediation_numerique")
    cda = next(e for e in content["cv"]["education"] if e["title"] == CDA)
    assert "status" not in cda


def test_la_mention_vae_reste_pour_une_variante_dev(master):
    content, _ = _assemble(master, "fullstack")
    cda = next(e for e in content["cv"]["education"] if e["title"] == CDA)
    assert cda.get("status") == "VAE en cours"


def test_un_diplome_obligatoire_manquant_est_signale(master):
    content, plan = _assemble(master, "mediation_numerique", education=[CDA])
    assert "MISSING_REQUIRED_EDUCATION" in _codes(content, master, plan)


def test_un_projet_interdit_pour_la_variante_est_signale(master):
    content, plan = _assemble(
        master, "mediation_numerique", projects=[{"id": "projet_documentation", "description": "Doc."}]
    )
    assert "FORBIDDEN_PROJECT_FOR_VARIANT" in _codes(content, master, plan)


def test_un_projet_reste_autorise_pour_une_variante_dev(master):
    content, plan = _assemble(
        master, "fullstack", projects=[{"id": "projet_documentation", "description": "Doc."}]
    )
    assert "FORBIDDEN_PROJECT_FOR_VARIANT" not in _codes(content, master, plan)


def test_les_experiences_obligatoires_ne_s_imposent_pas_a_la_mediation_sociale(master):
    proposed_without_required = {
        "experiences": [
            {"id": "studio_fictif", "bullets": [{"text": "Puce.", "sources": ["studio_fictif:0"]}]}
        ],
        "education": [],
    }
    plan = {"selected_base_variant": "mediation_sociale"}
    content = _assemble_cv_content(proposed_without_required, {}, master, plan, RUN, "test")
    assert "MISSING_REQUIRED_EXPERIENCE" not in _codes(content, master, plan)
    plan_dev = {"selected_base_variant": "fullstack"}
    content_dev = _assemble_cv_content(proposed_without_required, {}, master, plan_dev, RUN, "test")
    assert "MISSING_REQUIRED_EXPERIENCE" in _codes(content_dev, master, plan_dev)


def test_le_prompt_de_l_analyseur_ne_nomme_aucun_projet_en_dur():
    assert "DevDoc" not in ANALYZER_PROMPT


def test_le_prompt_de_l_analyseur_ne_contredit_pas_les_experiences_obligatoires():
    assert "aucun identifiant d'expérience n'est obligatoire" not in ANALYZER_PROMPT
    assert "Python ne\nréinjectera aucune expérience" not in ANALYZER_PROMPT


def test_le_paragraphe_des_consignes_n_existe_qu_une_fois_dans_le_code():
    from cv_generator import ai_agents as agents_module
    from cv_generator.rules import CANDIDATE_INSTRUCTIONS_CLAUSE

    source = Path(agents_module.__file__).read_text(encoding="utf-8")
    assert "source de vérité la plus haute" not in source
    for prompt in (
        agents_module.ANALYZER_PROMPT,
        agents_module.CREATOR_PROMPT,
        agents_module.REVIEWER_PROMPT,
        agents_module.REVISER_PROMPT,
    ):
        assert CANDIDATE_INSTRUCTIONS_CLAUSE in prompt


# ── Étape 2 : consignes du candidat (candidate_excludes) ─────────────────────

def test_mettre_en_avant_une_experience_ne_la_retire_pas(master):
    m = with_candidate_statements(master, "Mettre en avant Agence Exemple, sans cacher la formation.")
    assert candidate_excludes(m, "agence_exemple") is False


def test_retirer_un_autre_element_ne_retire_pas_l_experience_citee(master):
    m = with_candidate_statements(master, "Pas de mention du projet, insister sur Agence Exemple.")
    assert candidate_excludes(m, "agence_exemple") is False


def test_retirer_une_experience_par_son_nom_usuel(master):
    m = with_candidate_statements(master, "Retire Le Petit Studio.")
    assert candidate_excludes(m, "studio_fictif") is True


def test_retirer_une_experience_par_son_organisation_exacte(master):
    m = with_candidate_statements(master, "Retire Agence Exemple.")
    assert candidate_excludes(m, "agence_exemple") is True


# ── Étape 3 : une seule lecture de l'annonce ─────────────────────────────────

@pytest.mark.parametrize(
    "title",
    ["Médiateur numérique", "Conseiller numérique France Services", "Travailleur social (médiateur social)"],
)
def test_les_postes_de_mediation_reconnus_aujourd_hui(title):
    assert is_mediation_poste(title) is True


@_todo("3", "la famille de poste est devinée par une regex sur le seul titre")
@pytest.mark.parametrize("title", ["Chargé de médiation sociale", "Animateur numérique en médiathèque"])
def test_les_postes_de_mediation_non_reconnus(title):
    assert is_mediation_poste(title) is True


# ── Étape 5 : PDF de la lettre ───────────────────────────────────────────────

@_todo("5", "regenerate_letter_and_email produit le PDF sans le titre du poste")
def test_regenerer_une_lettre_de_mediation_garde_le_bandeau_sans_portfolio(tmp_path, monkeypatch):
    from applications import application_builder

    (tmp_path / "job.json").write_text(json.dumps({"title": "Médiateur numérique"}), encoding="utf-8")
    (tmp_path / "metadata.json").write_text(json.dumps({"files": {}}), encoding="utf-8")
    monkeypatch.setattr(
        application_builder,
        "generate_motivation_letter_with_report",
        lambda job, rec, profile: ("Lettre.", {"etat": "absent"}),
    )
    monkeypatch.setattr(application_builder, "generate_application_email", lambda *a: "Mail.")
    monkeypatch.setattr(application_builder, "_recommendation_from_metadata", lambda m, j: None)
    seen = {}
    monkeypatch.setattr(
        application_builder,
        "_write_letter_pdf",
        lambda path, directory, job_title="": seen.setdefault("title", job_title),
    )
    application_builder.regenerate_letter_and_email(tmp_path, "", "")
    assert seen["title"] == "Médiateur numérique"
