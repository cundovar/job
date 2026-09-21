import io
import json
from pathlib import Path

import pytest

from pypdf import PdfReader

from cv_generator import prepare_custom_cv
from cv_generator.ai_agents import (
    ANALYZER_PROMPT,
    CVAgentError,
    _check_completion,
    CREATOR_PROMPT,
    REVIEWER_PROMPT,
    REVISER_PROMPT,
    AgentResult,
    CVLLMClient,
    _merge_review,
    _assemble_cv_content,
    _standing_preference_clause,
    _validate_plan,
    build_correction_contract,
    correction_fingerprint,
)
from cv_generator.exporters import (
    DEFAULT_PORTRAIT,
    PDF_PORTRAIT_DIAMETER,
    _identity_baselines,
    cv_to_html,
    cv_to_markdown,
    cv_to_pdf,
)
from cv_generator.ats_exporter import cv_to_ats_html, cv_to_ats_pdf
from cv_generator.cv_assessment import evaluate_truthfulness
from cv_generator.cv_quality_checker import review_cv
from cv_generator.cv_creator import build_structural_shell
from cv_generator.layout import sparse_main_vertical_offset, title_requires_wrap, wrap_tracked_title
from cv_generator.job_analyzer import analyze_job_for_cv
from cv_generator.pipeline import _apply_final_review_status, _trace_item
from cv_generator.utils import load_json


CARECO = json.loads(
    (Path(__file__).parent / "fixtures" / "careco_cv_case.json").read_text(encoding="utf-8")
)


@pytest.fixture()
def careco_master(tmp_path):
    path = tmp_path / "master.json"
    path.write_text(json.dumps(CARECO["master"], ensure_ascii=False), encoding="utf-8")
    return path


class CarecoAgentClient:
    """Agent simulé qui écrit lui-même son bloc groupé et ses puces sourcées."""

    def __init__(self, *, experiences=None, projects=None, skills=None, education=None):
        self.calls = []
        self._experiences = experiences
        self._projects = projects
        self._skills = skills
        self._education = education

    def default_experiences(self):
        return [
            {
                "id": "missions_techniques_2026",
                "source_experience_ids": ["boutique_fictive", "atelier_imaginaire"],
                "bullets": [
                    {
                        "text": "Catalogue WooCommerce et API REST sur une boutique inventée.",
                        "sources": ["boutique_fictive:0", "boutique_fictive:1"],
                    },
                    {
                        "text": "Gabarits Twig et Bootstrap maintenus sur un site inventé.",
                        "sources": ["atelier_imaginaire:0"],
                    },
                    {
                        "text": "Travail en branches Git sur une base de code fictive.",
                        "sources": ["atelier_imaginaire:1"],
                    },
                ],
            },
            {
                "id": "permanence_test",
                "bullets": [
                    {
                        "text": "Accompagnement d'usagers fictifs sur des outils bureautiques.",
                        "sources": ["permanence_test:0"],
                    }
                ],
            },
        ]

    def complete_json(self, *, agent_name, system_prompt, payload):
        self.calls.append(agent_name)
        if agent_name == "cv_job_analyzer":
            data = {
                "selected_base_variant": "webmaster",
                "target_title": "Webmaster e-commerce",
                "positioning": "Webmaster de test, profil entierement invente.",
                "priority_keywords": ["WordPress", "WooCommerce", "Git"],
                "experience_plan": [
                    {"experience_id": "boutique_fictive", "priority": 10, "highlight_indexes": [0, 1]},
                    {"experience_id": "atelier_imaginaire", "priority": 9, "highlight_indexes": [0, 1]},
                    {"experience_id": "permanence_test", "priority": 5, "highlight_indexes": [0]},
                ],
                "presentation_strategy": {
                    "experience_display_mode": "grouped_missions",
                    "experience_group_id": "missions_techniques_2026",
                    "member_ids": ["boutique_fictive", "atelier_imaginaire"],
                },
                "section_order": ["profile", "skills", "experiences", "projects", "education"],
                "selected_projects": ["projet_vitrine"],
                "skills_to_emphasize": {
                    "cms": ["WordPress", "WooCommerce"],
                    "dev": ["Twig", "Bootstrap", "Git"],
                },
                "warnings": [],
            }
        elif agent_name in {"cv_creator", "cv_style_reviser"}:
            data = {
                "title": "Webmaster e-commerce",
                "profile": "Webmaster de test, profil entierement invente.",
                "skills": self._skills
                if self._skills is not None
                else [
                    {"title": "CMS", "items": ["WordPress", "WooCommerce"]},
                    {"title": "Développement", "items": ["Twig", "Bootstrap", "Git"]},
                ],
                "experiences": self._experiences
                if self._experiences is not None
                else self.default_experiences(),
                "projects": self._projects
                if self._projects is not None
                else [{"id": "projet_vitrine", "technologies": ["WordPress"]}],
                "education": self._education
                if self._education is not None
                else ["Titre professionnel Developpeur web (fictif)"],
            }
        elif agent_name == "cv_truth_checker":
            data = {"verdict": "accepted", "claims": [], "summary": "Toutes les puces sont sourcées."}
        elif agent_name == "cv_quality_checker":
            data = {
                "quality_score": 92,
                "ats_score": 90,
                "status": "validated",
                "strengths": ["Preuves techniques visibles."],
                "problems": [],
                "missing_keywords": [],
                "forbidden_claims_found": [],
                "verdict": "CV cohérent.",
            }
        else:
            raise AssertionError(f"Agent inattendu : {agent_name}")
        return AgentResult(data=data, provider="fake", model="fake-careco")



class FakeCVAgentClient(CarecoAgentClient):
    """Agent simulé par défaut, entièrement adossé à la fixture CARECO.

    Il enregistre aussi les charges utiles reçues : plusieurs tests vérifient
    ce que chaque rôle a — ou n'a pas — le droit de voir.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.payloads = []
        self.system_prompts = []

    def complete_json(self, *, agent_name, system_prompt, payload):
        self.payloads.append(payload)
        self.system_prompts.append(system_prompt)
        return super().complete_json(
            agent_name=agent_name, system_prompt=system_prompt, payload=payload
        )


class RetryCVAgentClient(FakeCVAgentClient):
    """Juge sévère deux fois, et réviseur qui corrige réellement entre deux passes."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.review_count = 0
        self.revision_count = 0

    def complete_json(self, *, agent_name, system_prompt, payload):
        result = super().complete_json(
            agent_name=agent_name, system_prompt=system_prompt, payload=payload
        )
        if agent_name == "cv_style_reviser":
            # Un vrai réviseur rend un contenu différent : sans cela, la
            # détection d'absence de progrès arrêterait la boucle à raison.
            self.revision_count += 1
            data = dict(result.data)
            experiences = [dict(item) for item in data["experiences"]]
            experiences[0] = dict(experiences[0])
            experiences[0]["bullets"] = [
                {
                    "text": f"Catalogue WooCommerce inventé (révision {self.revision_count}).",
                    "sources": ["boutique_fictive:0"],
                }
            ] + list(experiences[0]["bullets"][1:])
            data["experiences"] = experiences
            return AgentResult(data=data, provider=result.provider, model=result.model)
        if agent_name != "cv_quality_checker":
            return result
        self.review_count += 1
        if self.review_count > 2:
            return result
        data = dict(result.data)
        data["problems"] = [{
            "severity": "high",
            "section": "expériences",
            "problem": "Une preuve centrale manque encore.",
            "suggested_fix": "Rétablir la preuve prévue par le plan.",
        }]
        data["verdict"] = "Corriger puis relire"
        return AgentResult(data=data, provider=result.provider, model=result.model)


class AlwaysRetryCVAgentClient(FakeCVAgentClient):
    """Juge qui ne valide jamais, et réviseur qui ne change rien."""

    def complete_json(self, *, agent_name, system_prompt, payload):
        result = super().complete_json(
            agent_name=agent_name, system_prompt=system_prompt, payload=payload
        )
        if agent_name != "cv_quality_checker":
            return result
        data = dict(result.data)
        data["problems"] = [{
            "severity": "high",
            "section": "expériences",
            "problem": "Une preuve centrale manque encore.",
            "suggested_fix": "Rétablir la preuve prévue par le plan.",
        }]
        data["verdict"] = "Corriger puis relire"
        return AgentResult(data=data, provider=result.provider, model=result.model)


def _careco_cv(tmp_path, master_path, client):
    result = prepare_custom_cv(
        CARECO["job"], application_dir=tmp_path, master_path=master_path, llm_client=client
    )
    return result, json.loads((tmp_path / "cv" / "cv_content.json").read_text(encoding="utf-8"))


def test_prepare_custom_cv_generates_webmaster_files(tmp_path, careco_master):
    job = {
        "title": "Webmaster WordPress / administrateur de site",
        "company": "Ville Test",
        "description": "Gestion CMS WordPress, maintenance, contenus, documentation et sensibilisation RGAA.",
        "url": "https://example.test/job",
        "score": 90,
    }
    client = FakeCVAgentClient()

    result = prepare_custom_cv(
        job,
        application_dir=tmp_path,
        master_path=careco_master,
        llm_client=client,
    )

    assert result["ok"] is True
    assert result["pipeline"] == "ai_cv_pipeline_v4"
    assert result["selected_base_variant"] == "webmaster"
    assert "Webmaster" in result["target_title"]
    assert client.calls == [
        "cv_job_analyzer",
        "cv_creator",
        "cv_truth_checker",
        "cv_quality_checker",
    ]
    assert result["published"] is True
    assert (tmp_path / "cv" / "cv_final.json").exists()
    assert (tmp_path / "cv" / "cv_agent_trace.json").exists()
    assert (tmp_path / "cv" / "cv_final.html").exists()
    assert (tmp_path / "cv" / "cv_final.pdf").exists()
    assert (tmp_path / "cv" / "cv_ats.html").exists()
    assert (tmp_path / "cv" / "cv_ats.pdf").exists()
    assert (tmp_path / "cv" / "cv_assessment.json").exists()
    assert (tmp_path / "cv" / "cv_final.pdf").read_bytes().startswith(b"%PDF")
    assert (tmp_path / "cv" / "cv_ats.pdf").read_bytes().startswith(b"%PDF")
    assert not (tmp_path / "cv" / "cv_draft.md").exists()
    assert not (tmp_path / "cv" / "cv_final.md").exists()
    assert not (tmp_path / "cv" / "cv_canva_copy.md").exists()


def test_pipeline_automatically_applies_relevant_corrections_until_validated(tmp_path, careco_master):
    job = {
        "title": "Webmaster WordPress",
        "company": "Ville Test",
        "description": "Gestion CMS WordPress, maintenance, contenus et documentation utilisateurs.",
        "candidate_instructions": "Mettre en avant DevDoc sans inventer de compétence.",
    }
    client = RetryCVAgentClient()

    result = prepare_custom_cv(
        job,
        application_dir=tmp_path,
        master_path=careco_master,
        llm_client=client,
    )
    trace = json.loads((tmp_path / "cv" / "cv_agent_trace.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert trace["correction_retried"] is True
    assert trace["automatic_revision_rounds"] == 2
    assert trace["automatic_corrections_exhausted"] is False
    assert client.calls.count("cv_style_reviser") == 2
    assert client.calls.count("cv_quality_checker") == 3
    assert {
        payload["consignes_candidat"]
        for payload in client.payloads
        if "consignes_candidat" in payload
    } == {"Mettre en avant DevDoc sans inventer de compétence."}
    assert all(
        "candidate_instructions" not in payload["annonce_complete"]
        for payload in client.payloads
        if "annonce_complete" in payload
    )
    assert {
        "cv_job_analyzer",
        "cv_creator",
        "cv_quality_checker",
        "cv_style_reviser",
    } <= set(client.calls)
    assert trace["job"]["candidate_instructions_present"] is True
    assert trace["job"]["candidate_instructions_chars"] == 51
    assert "Mettre en avant DevDoc" not in json.dumps(trace, ensure_ascii=False)


def test_empty_candidate_instructions_preserve_the_existing_agent_contract(tmp_path, careco_master):
    job = {
        "title": "Webmaster WordPress",
        "company": "Ville Test",
        "description": "Gestion WordPress, maintenance et documentation utilisateurs.",
    }
    client = FakeCVAgentClient()

    prepare_custom_cv(
        job,
        application_dir=tmp_path,
        master_path=careco_master,
        llm_client=client,
    )
    trace = json.loads((tmp_path / "cv" / "cv_agent_trace.json").read_text(encoding="utf-8"))

    # Le vérificateur de vérité ne reçoit ni annonce ni consignes : il ne juge
    # que la provenance, pas la pertinence.
    assert all(
        payload["consignes_candidat"] == ""
        for payload in client.payloads
        if "consignes_candidat" in payload
    )
    assert trace["job"]["candidate_instructions_present"] is False
    assert trace["job"]["candidate_instructions_chars"] == 0
    for prompt in (ANALYZER_PROMPT, CREATOR_PROMPT, REVIEWER_PROMPT, REVISER_PROMPT):
        assert "consignes_candidat" in prompt
        assert "source de vérité" in prompt


def test_pipeline_stops_early_when_a_revision_makes_no_progress(tmp_path, careco_master):
    """Deux fois le même contenu et les mêmes reproches : on arrête, avec la cause."""
    job = {
        "title": "Webmaster WordPress",
        "company": "Ville Test",
        "description": "Gestion CMS WordPress, maintenance, contenus et documentation utilisateurs.",
    }
    client = AlwaysRetryCVAgentClient()

    result = prepare_custom_cv(
        job,
        application_dir=tmp_path,
        master_path=careco_master,
        llm_client=client,
    )
    trace = json.loads((tmp_path / "cv" / "cv_agent_trace.json").read_text(encoding="utf-8"))

    assert result["status"] == "review"
    assert trace["stopped_because"] == "no_progress"
    assert trace["automatic_revision_rounds"] < trace["automatic_revision_limit"]
    assert trace["automatic_corrections_exhausted"] is True


def test_persistent_revision_publishes_no_final_artefact(tmp_path, careco_master):
    """Un CV que le juge refuse encore ne produit aucun fichier `cv_final`."""
    job = {
        "title": "Webmaster WordPress",
        "company": "Ville Test",
        "description": "Gestion CMS WordPress, maintenance et documentation utilisateurs.",
    }

    result = prepare_custom_cv(
        job,
        application_dir=tmp_path,
        master_path=careco_master,
        llm_client=AlwaysRetryCVAgentClient(),
    )

    assert result["published"] is False
    assert result["status"] != "ready"
    for name in ("cv_final.json", "cv_final.html", "cv_final.pdf", "cv_ats.pdf", "cv_ats.html"):
        assert not (tmp_path / "cv" / name).exists(), name
    assert (tmp_path / "cv" / "cv_review_preview.pdf").read_bytes().startswith(b"%PDF")
    assert (tmp_path / "cv" / "cv_review_preview_ats.pdf").exists()
    assert (tmp_path / "cv" / "cv_content.json").exists()
    assert (tmp_path / "cv" / "cv_truth_check.json").exists()


def test_a_refused_regeneration_removes_the_previous_final_files(tmp_path, careco_master):
    """Le CV final d'un run précédent ne survit pas à un refus : il serait périmé."""
    job = {
        "title": "Webmaster WordPress",
        "company": "Ville Test",
        "description": "Gestion CMS WordPress, maintenance et documentation utilisateurs.",
    }

    prepare_custom_cv(
        job, application_dir=tmp_path, master_path=careco_master,
        llm_client=FakeCVAgentClient(),
    )
    assert (tmp_path / "cv" / "cv_final.pdf").exists()

    result = prepare_custom_cv(
        job, application_dir=tmp_path, master_path=careco_master,
        llm_client=AlwaysRetryCVAgentClient(),
    )

    assert result["published"] is False
    assert not (tmp_path / "cv" / "cv_final.pdf").exists()
    assert not (tmp_path / "cv" / "cv_ats.pdf").exists()
    trace = json.loads((tmp_path / "cv" / "cv_agent_trace.json").read_text(encoding="utf-8"))
    assert "cv_final.pdf" in trace["stale_artefacts_removed"]


def test_pdf_and_html_use_the_real_portrait(tmp_path):
    final_cv = {
        "cv": {
            "title": "Développeur full stack",
            "profile": "Développeur spécialisé en JavaScript et PHP, avec une expérience en architecture d'applications web modernes.",
            "contact": {"email": "varas.cundo@gmail.com", "phone": "06 23 84 84 45"},
            "location": "Paris / Île-de-France",
            "skills": [{"title": "Frontend", "items": ["JavaScript", "React", "Vue.js"]}],
            "experiences": [
                {
                    "period": "2025 / 2026",
                    "organization": "Pôle S",
                    "title": "Développeur web & formateur technique",
                    "bullets": ["Développement d'applications pédagogiques fullstack avec Symfony et Vue.js"],
                }
            ],
            "projects": [],
            "education": [{"year": "2022", "title": "Développeur Web et Web Mobile", "level": "Bac+2"}],
            "languages": [{"name": "Français", "level": "courant"}],
        }
    }

    assert DEFAULT_PORTRAIT.exists()
    html = cv_to_html(final_cv)
    assert "data:image/jpeg;base64," in html
    assert "Portrait de Facundo Varas" in html
    assert "justify-content: center" in html
    assert 'class="main-body sparse"' in html

    pdf_path = tmp_path / "cv.pdf"
    cv_to_pdf(final_cv, pdf_path)
    assert pdf_path.read_bytes().startswith(b"%PDF")
    assert pdf_path.stat().st_size > 10_000


def test_grouped_experience_renders_all_links_in_every_export(tmp_path):
    final_cv = {
        "cv": {
            "title": "Développeur web",
            "profile": "Profil test.",
            "contact": {},
            "skills": [],
            "experiences": [{
                "period": "2026-03 – Aujourd'hui",
                "organization": "La Magicieuse · Hélène Massage & Ayurveda",
                "title": "Missions et projets professionnels",
                "bullets": ["Deux missions regroupées."],
                "links": [
                    "https://www.la-magicieuse.org/",
                    "https://massagesdhelene.com/",
                ],
            }],
            "projects": [],
            "education": [],
            "languages": [],
        }
    }

    markdown = cv_to_markdown(final_cv)
    design_html = cv_to_html(final_cv)
    ats_html = cv_to_ats_html(final_cv)
    for expected in ("la-magicieuse.org", "massagesdhelene.com"):
        assert expected in markdown
        assert expected in design_html
        assert expected in ats_html

    design_pdf = tmp_path / "design.pdf"
    ats_pdf = tmp_path / "ats.pdf"
    cv_to_pdf(final_cv, design_pdf)
    cv_to_ats_pdf(final_cv, ats_pdf)
    for pdf_path in (design_pdf, ats_pdf):
        text = "\n".join(page.extract_text() or "" for page in PdfReader(pdf_path).pages)
        assert "la-magicieuse.org" in text
        assert "massagesdhelene.com" in text


def test_identity_block_is_centered_on_portrait():
    top = 812.0
    portrait_center = top - PDF_PORTRAIT_DIAMETER / 2

    name_y, target_y = _identity_baselines(top)

    assert name_y == portrait_center + 6.5
    assert target_y == portrait_center - 30.5


def test_sparse_main_content_is_centered_without_moving_dense_content():
    assert sparse_main_vertical_offset(240.0, 40.0, experience_count=2, has_projects=False) == 80.0
    assert sparse_main_vertical_offset(240.0, 40.0, experience_count=3, has_projects=False) == 0.0
    assert sparse_main_vertical_offset(240.0, 40.0, experience_count=2, has_projects=True) == 0.0
    assert sparse_main_vertical_offset(100.0, 40.0, experience_count=1, has_projects=False) == 0.0


def test_long_identity_title_wraps_instead_of_overflowing():
    title = "Conseiller numérique — formateur / médiateur numérique"

    assert title_requires_wrap(title)
    assert len(wrap_tracked_title(title)) == 2


def test_quality_checker_flags_long_identity_title():
    title = "Conseiller numérique — formateur / médiateur numérique"
    master = {
        "layout_constraints": {"max_profile_chars": 420, "max_bullet_chars": 145, "max_experiences": 4},
        "forbidden_claims": [],
    }
    plan = {"priority_keywords": [], "experience_plan": [{"experience_id": "exp"}]}
    draft = {
        "cv": {
            "title": title,
            "profile": "Profil formateur et conseiller numérique.",
            "experiences": [{"organization": "Test", "title": "Formateur", "bullets": ["Accompagnement numérique"]}],
        }
    }

    review = review_cv({}, master, plan, draft)

    assert any(problem["section"] == "header" for problem in review["problems"])


def test_hybrid_trainer_prompts_balance_real_work_pedagogy_and_ai():
    assert "trois piliers" in ANALYZER_PROMPT
    assert "réalisation technique réelle" in ANALYZER_PROMPT
    assert "aucun identifiant d'expérience n'est obligatoire" in ANALYZER_PROMPT
    assert "skills_confidence" in CREATOR_PROMPT
    assert "ordre antéchronologique" in CREATOR_PROMPT
    assert "formations en ligne ou à distance" in CREATOR_PROMPT
    assert "mairie_chelles" in ANALYZER_PROMPT
    assert "human_group_facilitation" in REVIEWER_PROMPT
    assert "écart honnête" in REVISER_PROMPT


def test_standing_preference_reaches_the_creator_from_the_master_not_the_prompt():
    """La préférence permanente vient du candidat, pas d'une constante Python."""
    master = {
        "adaptation_rules": {
            "standing_experience_preferences_by_variant": {"formateur_ia": ["mairie_chelles"]}
        }
    }
    plan = {"selected_base_variant": "formateur_ia"}

    assert "mairie_chelles" not in CREATOR_PROMPT
    assert "mairie_chelles" in _standing_preference_clause(master, plan, "creator")
    assert _standing_preference_clause(master, {"selected_base_variant": "webmaster"}, "creator") == ""


def test_agents_own_the_selection_contract_in_their_prompts():
    """Les prompts disent explicitement que Python ne complète plus rien."""
    assert "purement consultative" in ANALYZER_PROMPT
    assert "Python ne complète rien" in CREATOR_PROMPT
    assert "sources" in CREATOR_PROMPT
    assert "source_experience_ids" in CREATOR_PROMPT
    assert "Le moteur\nne regroupe plus à ta place" in CREATOR_PROMPT
    assert "Une puce sans source est refusée" in REVISER_PROMPT


def test_ai_review_owns_semantic_scores_and_verdict():
    proposed = {
        "quality_score": 91,
        "ats_score": 88,
        "status": "validated",
        "problems": [],
        "missing_keywords": [],
        "forbidden_claims_found": [],
        "verdict": "Le contenu est pertinent pour l'annonce.",
    }
    deterministic = {
        "quality_score": 42,
        "ats_score": 37,
        "status": "needs_revision",
        "problems": [{
            "severity": "medium",
            "section": "keywords",
            "problem": "Heuristique Python de pertinence.",
            "suggested_fix": "Ajouter un mot-clé.",
        }],
        "missing_keywords": ["PHP"],
        "forbidden_claims_found": [],
    }

    review = _merge_review(
        proposed,
        deterministic,
        AgentResult(data=proposed, provider="claude_cli", model="opus"),
        CARECO["master"],
    )

    assert review["quality_score"] == 91
    assert review["ats_score"] == 88
    assert review["status"] == "validated"
    assert review["problems"] == []
    assert review["missing_keywords"] == []


def test_ai_evidence_coverage_keeps_only_grounded_ids():
    """Un identifiant inventé par le juge est retiré, les identifiants réels restent."""
    master = CARECO["master"]
    proposed = {
        "quality_score": 86,
        "ats_score": 80,
        "status": "needs_minor_revision",
        "problems": [],
        "missing_keywords": [],
        "forbidden_claims_found": [],
        "evidence_coverage": [
            {
                "pillar": "pedagogy",
                "status": "covered",
                "experience_ids": ["permanence_test", "invented_training"],
                "project_ids": [],
                "gap": "",
            },
            {
                "pillar": "public_proof",
                "status": "partial",
                "experience_ids": ["boutique_fictive", "fake_client"],
                "project_ids": ["projet_vitrine", "fake_project"],
                "gap": "Afficher une réalisation publique pertinente.",
            },
        ],
    }

    review = _merge_review(
        proposed,
        {"problems": [], "forbidden_claims_found": []},
        AgentResult(data=proposed, provider="claude_cli", model="opus"),
        master,
    )

    assert review["evidence_coverage"] == [
        {
            "pillar": "pedagogy",
            "status": "covered",
            "experience_ids": ["permanence_test"],
            "project_ids": [],
            "gap": "",
        },
        {
            "pillar": "public_proof",
            "status": "partial",
            "experience_ids": ["boutique_fictive"],
            "project_ids": ["projet_vitrine"],
            "gap": "Afficher une réalisation publique pertinente.",
        },
    ]
    assert _trace_item(review)["evidence_coverage"] == review["evidence_coverage"]


def test_quality_checker_flags_an_overloaded_skill_block():
    master = {
        "layout_constraints": {
            "max_profile_chars": 240,
            "max_skill_items_total": 10,
            "max_bullet_chars": 145,
            "max_experiences": 4,
        },
        "forbidden_claims": [],
    }
    plan = {"priority_keywords": [], "experience_plan": [{"experience_id": "exp"}]}
    draft = {
        "cv": {
            "title": "Formateur",
            "profile": "Accompagnement de publics vers l'autonomie numérique.",
            "skills": [{"title": "Compétences", "items": [f"Compétence {index}" for index in range(11)]}],
            "experiences": [{"organization": "Test", "title": "Formateur", "bullets": ["Formation"]}],
        }
    }

    review = review_cv({}, master, plan, draft)

    assert any(problem["section"] == "skills" for problem in review["problems"])


def test_final_ai_review_overrides_a_conflicting_ready_status():
    assessment = {"overall_status": "ready", "match": {"score": 73}, "human_quality": {"score": 90}}
    review = {
        "status": "needs_revision",
        "quality_score": 87,
        "ats_score": 73,
        "verdict": "Corriger puis relire",
    }

    result = _apply_final_review_status(assessment, review)

    assert result["overall_status"] == "review"
    assert result["final_ai_review"]["status"] == "needs_revision"


def test_cv_llm_client_prefers_subscription_cli_bridge(monkeypatch):
    response = {
        "ok": True,
        "provider": "codex_cli",
        "model": "subscription-default",
        "data": {"status": "ok"},
    }

    class FakeSocket:
        def __init__(self):
            self.sent = b""
            self.timeout = None
            self.path = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def settimeout(self, timeout):
            self.timeout = timeout

        def connect(self, path):
            self.path = path

        def sendall(self, content):
            self.sent = content

        def makefile(self, mode):
            return io.BytesIO((json.dumps(response) + "\n").encode("utf-8"))

    fake_socket = FakeSocket()
    monkeypatch.setenv("CV_AI_PROVIDER_ORDER", "codex_cli")
    monkeypatch.setenv("CV_CLI_BRIDGE_TOKEN", "test-token-with-more-than-thirty-two-characters")
    monkeypatch.setenv("CV_CLI_BRIDGE_SOCKET", "/tmp/test-cv-bridge.sock")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("utils.cli_agent_bridge.socket.socket", lambda *args: fake_socket)

    result = CVLLMClient().complete_json(
        agent_name="cv_job_analyzer",
        system_prompt="Retourne du JSON.",
        payload={"job": {"title": "Webmaster"}},
    )

    request = json.loads(fake_socket.sent.decode("utf-8"))
    assert request["operation"] == "complete_json"
    assert request["agent_name"] == "cv_job_analyzer"
    assert request["payload"]["job"]["title"] == "Webmaster"
    assert request["preferred_provider"] == "codex"
    assert fake_socket.path == "/tmp/test-cv-bridge.sock"
    assert result.provider == "codex_cli"
    assert result.data == {"status": "ok"}


def test_quality_checker_reports_skill_without_visible_evidence():
    master = CARECO["master"]
    plan = {
        "selected_base_variant": "automatisation",
        "priority_keywords": ["MCP"],
        "evidence_matches": [{
            "requirement": "MCP",
            "evidence_id": "wordpress_mcp_pipeline",
            "project_ids": ["wp_site_builder"],
        }],
    }
    draft = {
        "base_variant": "automatisation",
        "cv": {
            "title": "Développeur automatisation",
            "profile": "Développement et intégrations MCP.",
            "skills": [{"title": "IA", "items": ["MCP (Model Context Protocol)"]}],
            "experiences": [],
            "projects": [],
        },
    }

    review = review_cv({"title": "Développeur MCP"}, master, plan, draft)

    assert "SKILL_WITHOUT_EVIDENCE" in review["problem_codes"]
    assert review["status"] == "needs_revision"


def test_empty_completion_names_the_exhausted_budget():
    """Une réponse vide doit se lire, pas se déboguer.

    Les modèles de raisonnement dépensent le budget de complétion avant
    d'écrire. Sans ce message, l'échec remontait en « n'a pas renvoyé un objet
    JSON », ce qui envoie chercher un bug de parsing là où il n'y a qu'un
    max_tokens trop court.
    """
    with pytest.raises(CVAgentError) as exhausted:
        _check_completion("", "length", 5000)
    message = str(exhausted.value)
    assert "budget" in message
    assert "CV_AI_MAX_TOKENS" in message
    assert "5000" in message

    with pytest.raises(CVAgentError) as empty:
        _check_completion("   ", "stop", 32000)
    assert "réponse vide" in str(empty.value)

    # Un contenu réel passe inchangé.
    assert _check_completion('{"ok": true}', "stop", 32000) == '{"ok": true}'


def _truthfulness_master(catalog_ids, group=None):
    """Maître minimal synthétique — jamais une copie du profil réel."""
    master = {
        "experience_catalog": {exp_id: {} for exp_id in catalog_ids},
        "experience_groups": {},
        "skills_confidence": {},
        "cv_variants": [],
        "forbidden_claims": [],
    }
    if group is not None:
        master["experience_groups"][group["id"]] = group
    return master


def _cv_with_experiences(*experiences):
    return {"cv": {"experiences": list(experiences)}}


def test_truthfulness_accepts_declared_group():
    """Un bloc groupé déclaré, avec membres au catalogue, n'est pas une invention."""
    master = _truthfulness_master(
        ["mission_a", "mission_b"],
        group={"id": "g1", "member_ids": ["mission_a", "mission_b"]},
    )
    final_cv = _cv_with_experiences(
        {"id": "g1", "source_experience_ids": ["mission_a", "mission_b"]}
    )

    result = evaluate_truthfulness(master, final_cv)

    assert result["status"] == "pass"
    assert result["issues"] == []


def test_truthfulness_accepts_declared_group_without_source_ids():
    """Sans source_experience_ids, les membres déclarés servent de référence."""
    master = _truthfulness_master(
        ["mission_a", "mission_b"],
        group={"id": "g1", "member_ids": ["mission_a", "mission_b"]},
    )
    final_cv = _cv_with_experiences({"id": "g1"})

    result = evaluate_truthfulness(master, final_cv)

    assert result["status"] == "pass"


def test_truthfulness_rejects_undeclared_group():
    """Un identifiant ni au catalogue ni dans experience_groups reste un échec."""
    master = _truthfulness_master(["mission_a"])
    final_cv = _cv_with_experiences({"id": "g1", "source_experience_ids": ["mission_a"]})

    result = evaluate_truthfulness(master, final_cv)

    assert result["status"] == "fail"
    assert result["issues"] == [{"type": "unknown_experience", "value": "g1"}]


def test_truthfulness_rejects_group_with_unknown_member():
    """Un groupe qui déclare un membre absent du catalogue unitaire est refusé."""
    master = _truthfulness_master(
        ["mission_a"],
        group={"id": "g1", "member_ids": ["mission_a", "mission_fantome"]},
    )
    final_cv = _cv_with_experiences({"id": "g1"})

    result = evaluate_truthfulness(master, final_cv)

    assert result["status"] == "fail"
    assert result["issues"] == [{"type": "unknown_experience", "value": "mission_fantome"}]
    assert result["details"][0]["code"] == "GROUP_MEMBER_NOT_IN_CATALOG"


def test_truthfulness_rejects_group_with_unexpected_source_ids():
    """Un bloc groupé qui s'appuie sur des membres non déclarés est refusé."""
    master = _truthfulness_master(
        ["mission_a", "mission_b"],
        group={"id": "g1", "member_ids": ["mission_a"]},
    )
    final_cv = _cv_with_experiences(
        {"id": "g1", "source_experience_ids": ["mission_a", "mission_b"]}
    )

    result = evaluate_truthfulness(master, final_cv)

    assert result["status"] == "fail"
    assert result["issues"] == [{"type": "unknown_experience", "value": "mission_b"}]
    assert result["details"][0]["code"] == "UNDECLARED_GROUP_MEMBER"


def test_final_review_cannot_downgrade_blocked():
    """L'avis IA ne débloque pas un contrôle Python en échec."""
    assessment = {"overall_status": "blocked"}
    final_review = {"status": "needs_revision"}

    result = _apply_final_review_status(assessment, final_review)

    assert result["overall_status"] == "blocked"


def test_final_review_downgrades_ready():
    """Une révision demandée retarde un CV prêt, sans le bloquer."""
    assessment = {"overall_status": "ready"}
    final_review = {"status": "needs_revision"}

    result = _apply_final_review_status(assessment, final_review)

    assert result["overall_status"] == "review"


# --------------------------------------------------------------------------- #
# Les agents décident, Python vérifie — cas CARECO, entièrement hors `data/`
# --------------------------------------------------------------------------- #

def test_careco_group_keeps_ecommerce_stack_and_support_evidence(tmp_path, careco_master):
    """Le défaut CARECO : le groupe ne conserve plus qu'une seule preuve."""
    result, final = _careco_cv(tmp_path, careco_master, CarecoAgentClient())

    grouped = final["cv"]["experiences"][0]
    assert grouped["id"] == "missions_techniques_2026"
    assert len(grouped["bullets"]) == 3
    text = " ".join(grouped["bullets"])
    assert "WooCommerce" in text or "API REST" in text
    assert "Twig" in text and "Bootstrap" in text
    assert "Git" in text
    assert "Accompagnement d'usagers" in " ".join(final["cv"]["experiences"][1]["bullets"])
    assert result["assessment"]["truthfulness"]["status"] == "pass"


def test_careco_never_invents_an_unsourced_requirement(tmp_path, careco_master):
    """Marketplace, comptabilité automobile et anglais restent des écarts honnêtes."""
    _, final = _careco_cv(tmp_path, careco_master, CarecoAgentClient())

    rendered = json.dumps(final["cv"], ensure_ascii=False).lower()
    for term in CARECO["unsourced_terms"]:
        assert term not in rendered


def test_python_never_reinjects_an_experience_the_agent_dropped(tmp_path, careco_master):
    """Une expérience écartée par le rédacteur reste absente du CV rendu."""
    client = CarecoAgentClient(experiences=CarecoAgentClient().default_experiences()[:1])

    _, final = _careco_cv(tmp_path, careco_master, client)

    assert [item["id"] for item in final["cv"]["experiences"]] == ["missions_techniques_2026"]


def test_python_preserves_the_order_chosen_by_the_agent(tmp_path, careco_master):
    """L'ordre rendu est celui de l'agent : Python le signale, ne le retrie pas."""
    reversed_experiences = list(reversed(CarecoAgentClient().default_experiences()))
    client = CarecoAgentClient(experiences=reversed_experiences)

    result, final = _careco_cv(tmp_path, careco_master, client)

    assert [item["id"] for item in final["cv"]["experiences"]] == [
        "permanence_test",
        "missions_techniques_2026",
    ]
    codes = {item["code"] for item in result["assessment"]["truthfulness"]["format_issues"]}
    assert "EXPERIENCE_ORDER_NOT_ANTICHRONOLOGICAL" in codes


def test_python_never_fabricates_a_fallback_bullet(tmp_path, careco_master):
    """Une expérience vide reste vide et devient une erreur, jamais une puce inventée."""
    experiences = CarecoAgentClient().default_experiences()
    experiences[1]["bullets"] = []
    client = CarecoAgentClient(experiences=experiences)

    result, final = _careco_cv(tmp_path, careco_master, client)

    assert final["cv"]["experiences"][1]["bullets"] == []
    codes = {item["code"] for item in result["assessment"]["truthfulness"]["format_issues"]}
    assert "EMPTY_EXPERIENCE" in codes


def test_python_does_not_group_when_the_agent_did_not_ask(tmp_path, careco_master):
    """Sans demande de l'agent, aucune mission n'est fusionnée par Python."""
    experiences = [
        {
            "id": "boutique_fictive",
            "bullets": [
                {"text": "Catalogue WooCommerce inventé.", "sources": ["boutique_fictive:0"]}
            ],
        },
        {
            "id": "atelier_imaginaire",
            "bullets": [
                {"text": "Gabarits Twig et Bootstrap inventés.", "sources": ["atelier_imaginaire:0"]}
            ],
        },
    ]
    client = CarecoAgentClient(experiences=experiences)

    _, final = _careco_cv(tmp_path, careco_master, client)

    assert [item["id"] for item in final["cv"]["experiences"]] == [
        "boutique_fictive",
        "atelier_imaginaire",
    ]


def test_agent_projects_and_education_survive_without_reinjection(tmp_path, careco_master):
    """Aucun projet ni diplôme n'est ajouté derrière le dos de l'agent."""
    client = CarecoAgentClient(projects=[], education=[])

    _, final = _careco_cv(tmp_path, careco_master, client)

    assert final["cv"]["projects"] == []
    assert final["cv"]["education"] == []


def test_creator_returning_no_experience_ends_in_review_not_a_crash(tmp_path, careco_master):
    """Une violation de contrat produit `review` et un diagnostic, jamais un faux échec."""
    client = CarecoAgentClient(experiences=[])

    result = prepare_custom_cv(
        CARECO["job"],
        application_dir=tmp_path,
        master_path=careco_master,
        llm_client=client,
    )

    assert result["ok"] is True
    assert result["status"] == "review"
    assert result["published"] is False
    assert (tmp_path / "cv" / "cv_agent_trace.json").exists()
    assert (tmp_path / "cv" / "cv_assessment.json").exists()
    assert (tmp_path / "cv" / "cv_adaptation_plan.json").exists()
    publication = result["assessment"]["publication"]
    assert publication["stopped_because"] == "agent_contract_violation"
    assert "aucune expérience" in publication["agent_error"]
    # Aucune dimension n'est mesurable sans contenu : aucune ne tranche.
    assert result["assessment"]["truthfulness"]["status"] == "review"


def test_analyzer_plan_is_kept_verbatim_without_quota(careco_master):
    """Le plan de l'analyste n'est ni complété ni plafonné par Python."""
    master = CARECO["master"]
    proposed = {
        "selected_base_variant": "webmaster",
        "experience_plan": [{"experience_id": "permanence_test", "highlight_indexes": [0]}],
    }

    plan = _validate_plan(
        proposed,
        analyze_job_for_cv(CARECO["job"], master),
        master,
        AgentResult(data={}, provider="test", model="test"),
    )

    assert [item["experience_id"] for item in plan["experience_plan"]] == ["permanence_test"]
    assert plan["presentation_strategy"] == {"experience_display_mode": "individual"}


def test_analyzer_plan_rejects_an_unknown_experience_without_replacing_it(careco_master):
    """Un identifiant inconnu est écarté et tracé, jamais remplacé par un autre."""
    master = CARECO["master"]
    proposed = {
        "selected_base_variant": "webmaster",
        "experience_plan": [
            {"experience_id": "mission_fantome"},
            {"experience_id": "permanence_test", "highlight_indexes": [0]},
        ],
    }

    plan = _validate_plan(
        proposed,
        analyze_job_for_cv(CARECO["job"], master),
        master,
        AgentResult(data={}, provider="test", model="test"),
    )

    assert [item["experience_id"] for item in plan["experience_plan"]] == ["permanence_test"]
    assert plan["unknown_experience_ids"] == ["mission_fantome"]


def test_analyzer_returning_nothing_is_a_contract_error(careco_master):
    """Python ne fabrique pas un plan à la place de l'agent analyste."""
    master = CARECO["master"]

    with pytest.raises(CVAgentError, match="aucune expérience"):
        _validate_plan(
            {"selected_base_variant": "webmaster", "experience_plan": []},
            analyze_job_for_cv(CARECO["job"], master),
            master,
            AgentResult(data={}, provider="test", model="test"),
        )


def test_preanalysis_only_suggests_and_imposes_no_minimum():
    """La préanalyse est un catalogue noté, sans quota ni expérience forcée."""
    plan = analyze_job_for_cv(CARECO["job"], CARECO["master"])

    assert "experience_plan" not in plan
    assert "selected_projects" not in plan
    assert "presentation_strategy" not in plan
    suggestions = plan["experience_suggestions"]
    assert {item["experience_id"] for item in suggestions} <= set(
        CARECO["master"]["experience_catalog"]
    )
    assert suggestions == sorted(suggestions, key=lambda item: item["priority"], reverse=True)


# --------------------------------------------------------------------------- #
# Vérité avant pertinence, révisions bornées, verrou d'export
# --------------------------------------------------------------------------- #


class InventingAgentClient(CarecoAgentClient):
    """Le rédacteur invente un fait que la preuve citée ne contient pas.

    Le réviseur reformule à chaque passe sans jamais retirer l'invention : la
    boucle progresse donc réellement, et c'est la limite de trois révisions qui
    l'arrête, pas la détection d'absence de progrès.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.revision_count = 0

    def complete_json(self, *, agent_name, system_prompt, payload):
        if agent_name == "cv_style_reviser":
            self.revision_count += 1
            result = super().complete_json(
                agent_name=agent_name, system_prompt=system_prompt, payload=payload
            )
            data = dict(result.data)
            experiences = [dict(item) for item in data["experiences"]]
            experiences[0] = dict(experiences[0])
            experiences[0]["bullets"] = [
                {
                    "text": f"Catalogue WooCommerce inventé (reformulation {self.revision_count}).",
                    "sources": ["boutique_fictive:0"],
                }
            ] + list(experiences[0]["bullets"][1:])
            data["experiences"] = experiences
            return AgentResult(data=data, provider="fake", model="fake-careco")
        if agent_name == "cv_truth_checker":
            self.calls.append(agent_name)
            return AgentResult(
                data={
                    "verdict": "refused",
                    "claims": [
                        {
                            "path": "experiences[0].bullets[0]",
                            "source_refs": ["boutique_fictive:0"],
                            "status": "unsupported",
                            "reason": "La preuve citée ne mentionne aucun chiffre d'affaires.",
                        }
                    ],
                    "summary": "Une affirmation non soutenue.",
                },
                provider="fake",
                model="fake-careco",
            )
        return super().complete_json(
            agent_name=agent_name, system_prompt=system_prompt, payload=payload
        )


def test_an_invention_blocks_before_the_recruiter_judge(tmp_path, careco_master):
    """Le vérificateur de vérité passe avant le juge, et son refus bloque."""
    client = InventingAgentClient()

    result = prepare_custom_cv(
        CARECO["job"], application_dir=tmp_path, master_path=careco_master, llm_client=client
    )

    assert client.calls.index("cv_truth_checker") < client.calls.index("cv_quality_checker")
    assert result["status"] == "blocked"
    assert result["published"] is False
    truth = json.loads((tmp_path / "cv" / "cv_truth_check.json").read_text(encoding="utf-8"))
    assert truth["verdict"] == "refused"
    assert truth["truth_issues"][0]["code"] == "CLAIM_NOT_SUPPORTED_BY_SOURCE"


def test_a_persistent_invention_exhausts_exactly_three_revisions(tmp_path, careco_master):
    """Trois passes de correction au maximum, chacune tracée."""
    client = InventingAgentClient()

    prepare_custom_cv(
        CARECO["job"], application_dir=tmp_path, master_path=careco_master, llm_client=client
    )
    trace = json.loads((tmp_path / "cv" / "cv_agent_trace.json").read_text(encoding="utf-8"))

    assert trace["automatic_revision_rounds"] == 3
    assert trace["automatic_revision_limit"] == 3
    assert trace["stopped_because"] == "revision_limit_reached"
    assert len(trace["rounds"]) == 3
    assert client.calls.count("cv_style_reviser") == 3
    assert client.calls.count("cv_truth_checker") == 4


def test_the_correction_contract_merges_truth_format_and_relevance():
    """Le réviseur reçoit les trois origines dans une liste unique et ordonnée."""
    review = {
        "problems": [
            {
                "code": "SKILL_WITHOUT_EVIDENCE",
                "section": "evidence",
                "problem": "Preuve absente.",
                "suggested_fix": "Ajouter une expérience sourcée.",
            }
        ]
    }
    truth_check = {
        "truth_issues": [
            {
                "code": "BULLET_WITHOUT_SOURCE",
                "path": "experiences[0].bullets[0]",
                "detail": "Aucune preuve citée.",
                "reference": None,
            }
        ],
        "format_issues": [
            {
                "code": "BULLET_TOO_LONG",
                "path": "experiences[0].bullets[1]",
                "detail": "Puce trop longue.",
                "reference": "exp",
            }
        ],
    }

    contract = build_correction_contract(review, truth_check)

    assert [item["origin"] for item in contract] == ["truth", "format", "relevance"]
    assert [item["blocking"] for item in contract] == [True, True, False]


def test_the_fingerprint_detects_an_unchanged_revision():
    """Même contenu et mêmes reproches produisent la même empreinte."""
    content = {"cv": {"title": "Webmaster", "experiences": []}}
    corrections = [{"origin": "truth", "code": "X", "location": "experiences[0]"}]

    assert correction_fingerprint(content, corrections) == correction_fingerprint(
        content, corrections
    )
    assert correction_fingerprint(content, corrections) != correction_fingerprint(
        {"cv": {"title": "Autre", "experiences": []}}, corrections
    )


def test_a_format_error_alone_holds_the_cv_in_review(tmp_path, careco_master):
    """Un dépassement de gabarit non résorbé retarde la publication sans bloquer."""
    experiences = CarecoAgentClient().default_experiences()
    experiences[0]["bullets"][0]["text"] = "Catalogue WooCommerce inventé. " * 12
    client = CarecoAgentClient(experiences=experiences)

    result = prepare_custom_cv(
        CARECO["job"], application_dir=tmp_path, master_path=careco_master, llm_client=client
    )

    assert result["status"] == "review"
    assert result["published"] is False
    assert not (tmp_path / "cv" / "cv_final.pdf").exists()
    codes = {item["code"] for item in result["assessment"]["publication"]["format_issues"]}
    assert "BULLET_TOO_LONG" in codes


def test_publication_block_reports_why_and_how_many_rounds(tmp_path, careco_master):
    """L'évaluation dit pourquoi le CV n'est pas final et combien de passes ont eu lieu."""
    result = prepare_custom_cv(
        CARECO["job"],
        application_dir=tmp_path,
        master_path=careco_master,
        llm_client=CarecoAgentClient(),
    )

    publication = result["assessment"]["publication"]
    assert publication["revision_rounds"] == 0
    assert publication["revision_limit"] == 3
    assert publication["stopped_because"] == "validated"
    assert publication["truth_verdict"] == "accepted"
    assert publication["blocking_issues"] == []
    assert result["published"] is True


def test_progress_file_follows_each_construction_step(tmp_path, careco_master):
    """L'interface doit pouvoir dire où en est la chaîne, pas juste « en cours »."""
    steps = []

    class RecordingClient(CarecoAgentClient):
        def complete_json(self, *, agent_name, system_prompt, payload):
            path = tmp_path / "cv" / "cv_progress.json"
            if path.exists():
                steps.append(json.loads(path.read_text(encoding="utf-8"))["step"])
            return super().complete_json(
                agent_name=agent_name, system_prompt=system_prompt, payload=payload
            )

    prepare_custom_cv(
        CARECO["job"],
        application_dir=tmp_path,
        master_path=careco_master,
        llm_client=RecordingClient(),
    )

    assert steps == ["analysis", "writing", "verification", "judgement"]
    final = json.loads((tmp_path / "cv" / "cv_progress.json").read_text(encoding="utf-8"))
    assert final["step"] == "done"
    assert final["status"] == "ready"
    assert final["revision_round"] == 0


def test_progress_counts_each_revision_round(tmp_path, careco_master):
    """Une correction en cours est visible, avec son numéro et sa limite."""
    rounds = []

    class RecordingClient(InventingAgentClient):
        def complete_json(self, *, agent_name, system_prompt, payload):
            path = tmp_path / "cv" / "cv_progress.json"
            if agent_name == "cv_style_reviser" and path.exists():
                rounds.append(json.loads(path.read_text(encoding="utf-8"))["revision_round"])
            return super().complete_json(
                agent_name=agent_name, system_prompt=system_prompt, payload=payload
            )

    prepare_custom_cv(
        CARECO["job"],
        application_dir=tmp_path,
        master_path=careco_master,
        llm_client=RecordingClient(),
    )

    assert rounds == [1, 2, 3]
    final = json.loads((tmp_path / "cv" / "cv_progress.json").read_text(encoding="utf-8"))
    assert final["step"] == "done"
    assert final["status"] == "blocked"
    assert final["revision_round"] == 3
    assert final["revision_limit"] == 3


# --- Non-régression : la panne observée en production le 21/09/2026 ---------- #


class NestedResponseClient(CarecoAgentClient):
    """Le réviseur répond `{"cv": {...}}` au lieu du schéma à plat.

    C'est la forme qu'un modèle recopie quand on lui montre la structure
    assemblée comme exemple. Elle faisait remonter une `CVAgentError` non gérée
    jusqu'au crash du sous-processus, sans aucun artefact écrit.
    """

    def complete_json(self, *, agent_name, system_prompt, payload):
        result = super().complete_json(
            agent_name=agent_name, system_prompt=system_prompt, payload=payload
        )
        if agent_name == "cv_style_reviser":
            return AgentResult(
                data={"cv": dict(result.data)}, provider="fake", model="fake-careco"
            )
        if agent_name == "cv_quality_checker":
            data = dict(result.data)
            data["status"] = "needs_revision"
            data["problems"] = [{
                "severity": "medium",
                "section": "evidence",
                "problem": "Une preuve manque.",
                "suggested_fix": "Ajouter une expérience sourcée.",
            }]
            return AgentResult(data=data, provider="fake", model="fake-careco")
        return result


def test_a_reviser_answering_in_the_wrong_shape_does_not_crash(tmp_path, careco_master):
    result = prepare_custom_cv(
        CARECO["job"],
        application_dir=tmp_path,
        master_path=careco_master,
        llm_client=NestedResponseClient(),
    )

    assert result["ok"] is True
    assert result["status"] == "review"
    assert result["published"] is False
    for name in ("cv_content.json", "cv_agent_trace.json", "cv_assessment.json", "cv_truth_check.json"):
        assert (tmp_path / "cv" / name).exists(), name
    trace = json.loads((tmp_path / "cv" / "cv_agent_trace.json").read_text(encoding="utf-8"))
    assert trace["stopped_because"] == "agent_contract_violation"
    assert "aucune expérience" in trace["agent_error"]


def test_the_last_valid_content_survives_a_reviser_failure(tmp_path, careco_master):
    """Le brouillon et son diagnostic portent sur le même CV : ils restent publiables."""
    result = prepare_custom_cv(
        CARECO["job"],
        application_dir=tmp_path,
        master_path=careco_master,
        llm_client=NestedResponseClient(),
    )

    content = json.loads((tmp_path / "cv" / "cv_content.json").read_text(encoding="utf-8"))
    assert [item["id"] for item in content["cv"]["experiences"]] == [
        "missions_techniques_2026",
        "permanence_test",
    ]
    assert result["assessment"]["truthfulness"]["status"] == "pass"


def test_a_crashing_regeneration_still_clears_the_previous_final_files(tmp_path, careco_master):
    """Le chemin d'erreur ne doit pas laisser survivre un CV final périmé."""
    prepare_custom_cv(
        CARECO["job"], application_dir=tmp_path, master_path=careco_master,
        llm_client=CarecoAgentClient(),
    )
    assert (tmp_path / "cv" / "cv_final.pdf").exists()

    prepare_custom_cv(
        CARECO["job"], application_dir=tmp_path, master_path=careco_master,
        llm_client=CarecoAgentClient(experiences=[]),
    )

    assert not (tmp_path / "cv" / "cv_final.pdf").exists()
    assert not (tmp_path / "cv" / "cv_ats.pdf").exists()


def test_the_reviser_receives_the_shape_it_must_return(tmp_path, careco_master):
    """La cause racine : le réviseur doit voir le schéma à plat, pas l'assemblé."""
    client = CarecoAgentClient()
    captured = {}

    class Capturing(CarecoAgentClient):
        def complete_json(self, *, agent_name, system_prompt, payload):
            if agent_name == "cv_style_reviser":
                captured.update(payload["brouillon"])
            return super().complete_json(
                agent_name=agent_name, system_prompt=system_prompt, payload=payload
            )

    prepare_custom_cv(
        CARECO["job"], application_dir=tmp_path, master_path=careco_master,
        llm_client=Capturing(experiences=[
            {"id": "permanence_test", "bullets": [
                {"text": "Puce trop longue. " * 12, "sources": ["permanence_test:0"]}
            ]},
        ]),
    )

    assert "cv" not in captured
    assert {"title", "profile", "skills", "experiences", "projects", "education"} <= set(captured)
    bullet = captured["experiences"][0]["bullets"][0]
    assert set(bullet) == {"text", "sources"}
    assert bullet["sources"] == ["permanence_test:0"]


def test_a_truncated_answer_names_the_budget_not_a_contract_violation():
    """Une réponse coupée doit dire « tronquée », pas « aucune expérience »."""
    from cv_generator.ai_agents import _parse_json_response

    with pytest.raises(CVAgentError, match="tronquée"):
        _parse_json_response('{"title":"W","experiences":[{"id":"a","bullets":[{"text":"Une')

    with pytest.raises(CVAgentError, match="budget de complétion"):
        _check_completion('{"title":"W"', "length", 32000)
