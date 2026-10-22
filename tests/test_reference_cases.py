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


@pytest.mark.parametrize("title", ["Chargé de médiation sociale", "Animateur numérique en médiathèque"])
def test_les_postes_de_mediation_autrefois_non_reconnus(title):
    assert is_mediation_poste(title) is True


def test_la_famille_de_l_analyse_prime_sur_l_intitule():
    assert is_mediation_poste({"title": "Description de la mission", "job_family": "mediation_sociale"})
    assert not is_mediation_poste({"title": "Médiateur", "job_family": "developpement"})


PLAN = {
    "annonce": {
        "intitule": "Médiateur social",
        "entreprise": "Association Fictive",
        "lieu": "Ville-Exemple",
        "contrat": "CDD",
        "famille": "mediation_sociale",
    },
    "selected_base_variant": "mediation_sociale",
    "priority_keywords": ["accueil", "orientation"],
    "experience_plan": [{"experience_id": "agence_exemple"}],
}


def test_l_analyse_complete_une_annonce_collee_sans_ecraser_la_saisie():
    from applications.application_builder import enrich_job_from_analysis

    pasted = {"title": "Description du poste", "title_inferred": True, "company": "Entreprise de l'annonce"}
    enriched = enrich_job_from_analysis(pasted, PLAN)
    assert enriched["title"] == "Médiateur social"
    assert enriched["company"] == "Association Fictive"
    assert enriched["contract_type"] == "CDD"
    assert enriched["job_family"] == "mediation_sociale"
    typed = {"title": "Chargé d'accueil", "company": "Mairie Fictive", "location": "Ailleurs"}
    kept = enrich_job_from_analysis(typed, PLAN)
    assert (kept["title"], kept["company"], kept["location"]) == ("Chargé d'accueil", "Mairie Fictive", "Ailleurs")


def _prepare(tmp_path, monkeypatch, master, analyze):
    from applications import application_builder

    letters = []

    def fake_letter(job, recommendation, profile, master=None):
        letters.append((job, recommendation, master))
        return "Lettre.", {"etat": "absent"}

    monkeypatch.setattr(application_builder, "generate_motivation_letter_with_report", fake_letter)
    monkeypatch.setattr(application_builder, "generate_application_email", lambda *a, **k: "Mail.")
    monkeypatch.setattr(application_builder, "summarize_job", lambda job: type("S", (), {"to_markdown": lambda self: ""})())
    monkeypatch.setattr(application_builder, "_write_letter_pdf", lambda *a, **k: None)
    job = {
        "title": "Description du poste",
        "title_inferred": True,
        "company": "Entreprise de l'annonce",
        "source": "annonce_manuelle",
        "description": "Accueil, orientation et ateliers pour des résidents.",
    }
    package = application_builder.build_application_package(
        job, output_dir=str(tmp_path), master=master, analyze=analyze
    )
    return package, letters


def test_la_lettre_et_le_cv_partent_de_la_meme_lecture_de_l_annonce(tmp_path, monkeypatch, master):
    from cv_generator.offer_analysis import load_offer_analysis

    package, letters = _prepare(tmp_path, monkeypatch, master, lambda job, m: PLAN)
    job, recommendation, given_master = letters[0]
    assert recommendation.cv_id == "mediation_sociale"
    assert job["job_family"] == "mediation_sociale"
    assert given_master is master
    assert "association-fictive_mediateur-social" in package.directory
    assert package.job["title"] == "Médiateur social"
    assert load_offer_analysis(package.directory, package.job)["selected_base_variant"] == "mediation_sociale"


def test_sans_analyse_la_lettre_retombe_sur_les_mots_cles(tmp_path, monkeypatch, master):
    package, letters = _prepare(tmp_path, monkeypatch, master, lambda job, m: None)
    assert letters[0][1].cv_id in {v["id"] for v in master["cv_variants"]}
    assert not (Path(package.directory) / "cv" / "offer_analysis.json").exists()


def test_le_plan_n_est_reutilise_que_pour_la_meme_annonce(tmp_path):
    from cv_generator.offer_analysis import load_offer_analysis, save_offer_analysis

    job = {"description": "Annonce A", "candidate_instructions": "Mettre en avant l'accueil."}
    save_offer_analysis(tmp_path, job, PLAN)
    assert load_offer_analysis(tmp_path, job) == PLAN
    assert load_offer_analysis(tmp_path, {**job, "description": "Annonce B"}) is None
    assert load_offer_analysis(tmp_path, {**job, "candidate_instructions": "Autre consigne."}) is None


def test_deux_annonces_collees_au_meme_intitule_ne_s_ecrasent_pas(tmp_path):
    from applications.application_tracker import ApplicationTracker

    tracker = ApplicationTracker(str(tmp_path / "tracker.json"))
    a = {"title": "Description du poste", "company": "X", "source": "annonce_manuelle", "description": "A"}
    b = {**a, "description": "B"}
    assert tracker.job_key(a) != tracker.job_key(b)
    scraped = {"title": "Poste", "company": "X", "description": "A"}
    assert tracker.job_key(scraped) == "Poste-X"


def test_la_lettre_recoit_le_profil_maitre_sans_donnees_privees(master):
    from agents.motivation_letter_agent import _build_payload
    from applications.cv_selector import recommendation_from_plan

    master["experience_catalog"]["boutique_imaginaire"]["retired"] = True
    recommendation = recommendation_from_plan(PLAN, master)
    payload = _build_payload(
        {"title": "Médiateur social", "job_family": "mediation_sociale"},
        recommendation,
        {"status": "CSP", "salaire_cible": "40 k€", "email": "x"},
        master,
    )
    profil = payload["profil"]
    text = json.dumps(payload, ensure_ascii=False)
    assert "CSP" not in text and "40 k€" not in text
    assert payload["famille_poste"] == "mediation_sociale"
    assert "boutique_imaginaire" not in {e["id"] for e in profil["experiences"]}
    assert "projet_documentation" not in {p["id"] for p in profil["projets"]}
    assert all("status" not in e for e in profil["formation"])
    sans_master = _build_payload({"title": "x"}, recommendation, {"status": "CSP", "email": "x"}, None)
    assert sans_master["profil"] == {"email": "x"}


# ── Étape 5 : PDF de la lettre ───────────────────────────────────────────────

def test_regenerer_une_lettre_de_mediation_garde_le_bandeau_sans_portfolio(tmp_path, monkeypatch):
    from applications import application_builder

    job = {"title": "Description de la mission", "job_family": "mediation_sociale"}
    (tmp_path / "job.json").write_text(json.dumps(job), encoding="utf-8")
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
        lambda path, directory, job: seen.setdefault("job", job),
    )
    application_builder.regenerate_letter_and_email(tmp_path, "", "")
    from cv_generator.rules import is_mediation_job

    assert is_mediation_job(seen["job"])


# ── Étape 5 : un seul chemin pour le PDF de la lettre côté serveur ───────────

def test_le_pdf_de_lettre_du_serveur_suit_les_regles_du_dossier(tmp_path, monkeypatch):
    from applications import letter_pdf

    (tmp_path / "lettre_motivation.md").write_text("Lettre.", encoding="utf-8")
    (tmp_path / "job.json").write_text(json.dumps({"title": "Chargé de médiation sociale"}), encoding="utf-8")
    seen = {}

    def fake_write(letter, directory, job):
        seen["job"] = job
        return directory / "lettre_motivation.pdf"

    monkeypatch.setattr(letter_pdf, "_write_letter_pdf", fake_write)
    letter_pdf.write_dossier_letter_pdf(tmp_path)
    assert seen["job"]["title"] == "Chargé de médiation sociale"
    with pytest.raises(FileNotFoundError):
        letter_pdf.write_dossier_letter_pdf(tmp_path / "absent")


# ── Étape 6 : les coordonnées ne partent pas aux fournisseurs d'IA ───────────

def test_telephone_et_email_ne_partent_a_aucun_agent(master):
    from cv_generator.ai_agents import AICVPipeline

    phone = master["person"]["contact"]["phone"]
    email = master["person"]["contact"]["email"]
    payloads = []

    class Recorder:
        def complete_json(self, *, agent_name, system_prompt, payload):
            payloads.append((agent_name, json.dumps(payload, ensure_ascii=False)))
            if agent_name == "cv_job_analyzer":
                return {"selected_base_variant": "fullstack", "experience_plan": [{"experience_id": "agence_exemple"}]}
            if agent_name == "cv_truth_checker":
                return {"verdict": "accepted", "claims": []}
            if agent_name == "cv_quality_checker":
                return {"status": "validated", "problems": [], "quality_score": 90, "ats_score": 90}
            return {
                "title": "Titre",
                "profile": "Accroche.",
                "skills": [],
                "experiences": [{"id": "agence_exemple", "bullets": [{"text": "Puce.", "sources": ["agence_exemple:0"]}]}],
                "projects": [],
                "education": [],
            }

    agents = AICVPipeline(Recorder())
    job = {"title": "Développeur", "description": "PHP Symfony"}
    plan = agents.analyze(job, master)
    draft = agents.create(job, master, plan)
    assert draft["cv"]["contact"]["email"] == email  # Python les remet dans le CV
    agents.verify(job, master, plan, draft)
    agents.review(job, master, plan, draft)
    assert {name for name, _ in payloads} >= {"cv_job_analyzer", "cv_creator", "cv_truth_checker", "cv_quality_checker"}
    for name, text in payloads:
        assert phone not in text and email not in text, name


# ── Expérience déclarée dans les consignes (décision Cundo 22/10/2026) ───────

from cv_generator.cv_truth_validator import with_candidate_statements as _with_statements
from cv_generator.declared_experiences import validate_declared, with_declared_experiences

CONSIGNE_VENDEUR = (
    "Ajoute mon expérience de vendeur chez Magasin Fictif depuis septembre 2026. "
    "J'y conseille les clients et je gère la mise en rayon."
)


def _master_consigne(master):
    return _with_statements(master, CONSIGNE_VENDEUR)


def test_experience_declaree_reduite_a_ce_que_dit_la_consigne(master):
    m = _master_consigne(master)
    kept, warnings = validate_declared(
        [{"id": "x", "organization": "Magasin Fictif", "title": "vendeur", "start": "2026-09",
          "end": "", "ongoing": True, "statement_indexes": [0, 1]}],
        m,
    )
    assert len(kept) == 1 and not warnings
    entry = kept[0]
    assert entry["id"].startswith("declaree_")
    assert entry["period"] == {"start": "2026-09", "ongoing": True}
    assert entry["highlights"] == m["candidate_statements"][:2]


def test_rien_d_invente_dans_une_experience_declaree(master):
    m = _master_consigne(master)
    kept, warnings = validate_declared(
        [{"organization": "Enseigne Inventée", "title": "vendeur", "start": "2025-03",
          "end": "2026-01", "statement_indexes": [0]}],
        m,
    )
    entry = kept[0]
    assert entry["organization"] == ""          # absente de la consigne
    assert entry["title"] == "vendeur"
    assert entry["period"] == {}                # ni 2025 ni 2026-01 ne sont écrits ainsi
    assert any("Enseigne Inventée" in w for w in warnings)


def test_sans_phrase_citee_ou_sans_consigne_rien_n_est_cree(master):
    assert validate_declared([{"organization": "Magasin Fictif", "statement_indexes": []}], _master_consigne(master))[0] == []
    assert validate_declared([{"organization": "Magasin Fictif", "statement_indexes": [0]}], master)[0] == []


def test_l_experience_declaree_entre_dans_le_plan_meme_omise_par_l_analyste(master):
    from cv_generator.ai_plan import _validate_plan

    m = _master_consigne(master)
    proposed = {
        "selected_base_variant": "fullstack",
        "experiences_declarees": [
            {"id": "vendeur", "organization": "Magasin Fictif", "title": "vendeur", "start": "2026-09",
             "ongoing": True, "statement_indexes": [0, 1]}
        ],
        "experience_plan": [{"experience_id": "agence_exemple", "highlight_indexes": [0]}],
    }
    plan = _validate_plan(proposed, {"selected_base_variant": "fullstack"}, m, RUN)
    declared_id = plan["declared_experiences"][0]["id"]
    assert declared_id in [item["experience_id"] for item in plan["experience_plan"]]

    # Citée par l'analyste sous son propre id : renommée, pas dupliquée.
    proposed["experience_plan"].insert(0, {"experience_id": "vendeur", "highlight_indexes": [0]})
    plan = _validate_plan(proposed, {"selected_base_variant": "fullstack"}, m, RUN)
    ids = [item["experience_id"] for item in plan["experience_plan"]]
    assert ids.count(declared_id) == 1 and ids[0] == declared_id


def test_cv_avec_experience_declaree_sans_erreur_de_verite_et_absence_signalee(master):
    m = _master_consigne(master)
    kept, _ = validate_declared(
        [{"organization": "Magasin Fictif", "title": "vendeur", "start": "2026-09", "ongoing": True,
          "statement_indexes": [0, 1]}],
        m,
    )
    m = with_declared_experiences(m, kept)
    exp_id = kept[0]["id"]
    proposed = {
        "title": "Titre", "profile": "Accroche.", "skills": [], "projects": [], "education": [CDA],
        "experiences": [
            {"id": exp_id, "bullets": [{"text": "Conseil des clients et mise en rayon.", "sources": [f"{exp_id}:1"]}]},
            {"id": "agence_exemple", "bullets": [{"text": "Puce.", "sources": ["agence_exemple:0"]}]},
        ],
    }
    plan = {"selected_base_variant": "fullstack"}
    content = _assemble_cv_content(proposed, {"title": "Poste"}, m, plan, RUN, "test")
    issues = validate_cv_content(content, m, plan)["issues"]
    assert not [i for i in issues if i["kind"] == "truth"], issues
    assert content["cv"]["experiences"][0]["period"] == "2026-09 – Aujourd'hui"

    proposed["experiences"] = proposed["experiences"][1:]
    content = _assemble_cv_content(proposed, {"title": "Poste"}, m, plan, RUN, "test")
    assert "MISSING_DECLARED_EXPERIENCE" in _codes(content, m, plan)
