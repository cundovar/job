import io
import json

from cv_generator import prepare_custom_cv
from cv_generator.ai_agents import AgentResult, CVLLMClient, _merge_review, _sanitize_cv_content, _sanitize_plan
from cv_generator.exporters import (
    DEFAULT_PORTRAIT,
    PDF_PORTRAIT_DIAMETER,
    _identity_baselines,
    cv_to_html,
    cv_to_pdf,
)
from cv_generator.cv_quality_checker import review_cv
from cv_generator.cv_creator import create_cv_draft
from cv_generator.layout import sparse_main_vertical_offset, title_requires_wrap, wrap_tracked_title
from cv_generator.job_analyzer import _experience_plan, analyze_job_for_cv
from cv_generator.pipeline import _apply_final_review_status
from cv_generator.utils import load_json


class FakeCVAgentClient:
    def __init__(self):
        self.calls = []

    def complete_json(self, *, agent_name, system_prompt, payload):
        self.calls.append(agent_name)
        if agent_name == "cv_job_analyzer":
            data = {
                "selected_base_variant": "webmaster",
                "target_title": "Webmaster / Administrateur de sites web",
                "positioning": "Webmaster orienté WordPress, maintenance et accompagnement des utilisateurs.",
                "priority_keywords": ["WordPress", "maintenance"],
                "experience_plan": [
                    {
                        "experience_id": "la_magicieuse",
                        "priority": 10,
                        "reason": "Expérience WordPress récente.",
                        "highlight_indexes": [0],
                    },
                    {
                        "experience_id": "freelance_wordpress",
                        "priority": 8,
                        "reason": "Administration et refonte WordPress.",
                        "highlight_indexes": [0, 1],
                    },
                ],
                "skills_to_emphasize": {
                    "web_cms": ["WordPress", "Maintenance"],
                    "support": ["Documentation technique"],
                },
                "skills_to_reduce": [],
                "warnings": ["Ne pas survendre le niveau RGAA."],
            }
        elif agent_name in {"cv_creator", "cv_style_reviser"}:
            data = {
                "title": "Webmaster / Administrateur de sites web",
                "profile": "Webmaster orienté WordPress, maintenance de sites et accompagnement des utilisateurs.",
                "skills": [
                    {"title": "Web / CMS", "items": ["WordPress", "Maintenance"]},
                    {"title": "Support", "items": ["Documentation technique"]},
                ],
                "experiences": [
                    {
                        "id": "la_magicieuse",
                        "bullets": [
                            {
                                "text": "Développement d'un site e-commerce headless pour une maison d'édition",
                                "source_highlight_indexes": [0],
                            }
                        ],
                    },
                    {
                        "id": "freelance_wordpress",
                        "bullets": [
                            {
                                "text": "Refonte complète et personnalisation de sites WordPress",
                                "source_highlight_indexes": [0, 1],
                            }
                        ],
                    },
                ],
                "projects": [],
            }
        elif agent_name == "cv_quality_checker":
            data = {
                "quality_score": 96,
                "ats_score": 94,
                "status": "validated",
                "strengths": ["Contenu ciblé et correctement sourcé."],
                "problems": [],
                "missing_keywords": [],
                "overrepresented_keywords": [],
                "forbidden_claims_found": [],
                "verdict": "CV cohérent avec l'annonce et le profil.",
            }
        else:
            raise AssertionError(f"Unexpected agent: {agent_name}")
        return AgentResult(data=data, provider="fake", model="fake-cv-model")


class RetryCVAgentClient(FakeCVAgentClient):
    def __init__(self):
        super().__init__()
        self.review_count = 0

    def complete_json(self, *, agent_name, system_prompt, payload):
        result = super().complete_json(
            agent_name=agent_name,
            system_prompt=system_prompt,
            payload=payload,
        )
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
    def complete_json(self, *, agent_name, system_prompt, payload):
        result = super().complete_json(
            agent_name=agent_name,
            system_prompt=system_prompt,
            payload=payload,
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


def test_prepare_custom_cv_generates_webmaster_files(tmp_path):
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
        master_path="data/cv_master_profile.json",
        llm_client=client,
    )

    assert result["ok"] is True
    assert result["pipeline"] == "ai_cv_pipeline_v3"
    assert result["selected_base_variant"] == "webmaster"
    assert "Webmaster" in result["target_title"]
    assert client.calls == [
        "cv_job_analyzer",
        "cv_creator",
        "cv_quality_checker",
    ]
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


def test_pipeline_automatically_applies_relevant_corrections_until_validated(tmp_path):
    job = {
        "title": "Webmaster WordPress",
        "company": "Ville Test",
        "description": "Gestion CMS WordPress, maintenance, contenus et documentation utilisateurs.",
    }
    client = RetryCVAgentClient()

    result = prepare_custom_cv(
        job,
        application_dir=tmp_path,
        master_path="data/cv_master_profile.json",
        llm_client=client,
    )
    trace = json.loads((tmp_path / "cv" / "cv_agent_trace.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert trace["correction_retried"] is True
    assert trace["automatic_revision_rounds"] == 2
    assert trace["automatic_corrections_exhausted"] is False
    assert client.calls.count("cv_style_reviser") == 2
    assert client.calls.count("cv_quality_checker") == 3


def test_pipeline_stops_automatic_corrections_at_the_safety_limit(tmp_path):
    job = {
        "title": "Webmaster WordPress",
        "company": "Ville Test",
        "description": "Gestion CMS WordPress, maintenance, contenus et documentation utilisateurs.",
    }
    client = AlwaysRetryCVAgentClient()

    result = prepare_custom_cv(
        job,
        application_dir=tmp_path,
        master_path="data/cv_master_profile.json",
        llm_client=client,
    )
    trace = json.loads((tmp_path / "cv" / "cv_agent_trace.json").read_text(encoding="utf-8"))

    assert result["status"] == "review"
    assert trace["automatic_revision_rounds"] == 3
    assert trace["automatic_corrections_exhausted"] is True
    assert client.calls.count("cv_style_reviser") == 3
    assert client.calls.count("cv_quality_checker") == 4


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


def test_mediation_variant_prioritizes_pedagogy_and_ai_without_forcing_web_languages():
    master = load_json("data/cv_master_profile.json")
    job = {
        "title": "Animateur conseiller numérique",
        "description": "Accompagnement numérique, ateliers, autonomie et inclusion numérique.",
    }

    plan = analyze_job_for_cv(job, master)
    konexio = master["experience_catalog"]["konexio_formateur_benevole"]

    assert plan["selected_base_variant"] == "formateur_generaliste"
    assert "konexio_formateur_benevole" in [item["experience_id"] for item in plan["experience_plan"]]
    assert "IA" in plan["positioning"]
    assert konexio["period"] == {"start": "2023-01", "end": "2023-07", "date_confidence": "confirmed_by_user"}
    assert "ia" not in konexio["tags"]
    assert any("HTML" in highlight and "CSS" in highlight and "JavaScript" in highlight for highlight in konexio["highlights"])
    variant = next(item for item in master["cv_variants"] if item["id"] == "formateur_generaliste")
    assert "ChatGPT" in variant["skills"]["tools"]
    assert "Claude" in variant["skills"]["tools"]
    emphasized = {item for items in plan["skills_to_emphasize"].values() for item in items}
    assert {"Animation de groupe", "Accompagnement numérique", "ChatGPT", "Claude"} <= emphasized
    assert "PHP 8" not in emphasized
    assert "JavaScript ES6+" not in emphasized


def test_conditional_education_is_selected_from_job_keywords():
    master = load_json("data/cv_master_profile.json")
    job = {"title": "Animateur petite enfance", "description": "Animation auprès d'enfants."}
    plan = analyze_job_for_cv(job, master)
    draft = create_cv_draft(job, master, plan)

    assert any(item["title"] == "CAP Petite Enfance" for item in draft["cv"]["education"])


def test_human_training_job_selects_cap_and_bac_l():
    master = load_json("data/cv_master_profile.json")
    job = {
        "title": "Conseiller formateur",
        "description": "Approche humaine, accompagnement et gestion de groupe.",
    }
    plan = analyze_job_for_cv(job, master)
    education = create_cv_draft(job, master, plan)["cv"]["education"]
    titles = [item["title"] for item in education]

    assert "CAP Petite Enfance" in titles
    assert "Bac L option cinéma audiovisuel" in titles
    assert "Développeur Web et Web Mobile" in titles
    assert "Titre Professionnel Concepteur Développeur d'Applications" in titles
    assert "secom_gard" not in [item["experience_id"] for item in plan["experience_plan"]]


def test_cultural_job_selects_bac_l():
    master = load_json("data/cv_master_profile.json")
    job = {
        "title": "Médiateur culturel en bibliothèque",
        "description": "Animation autour du livre, de la lecture et du patrimoine.",
    }
    plan = analyze_job_for_cv(job, master)
    education = create_cv_draft(job, master, plan)["cv"]["education"]

    assert any(item["title"] == "Bac L option cinéma audiovisuel" for item in education)


def test_group_management_job_selects_animation_experience():
    master = load_json("data/cv_master_profile.json")
    job = {
        "title": "Formateur adultes",
        "description": "Animation et gestion de groupe, accompagnement des participants.",
    }
    plan = analyze_job_for_cv(job, master)

    assert "mairie_chelles" in [item["experience_id"] for item in plan["experience_plan"]]


def test_cultural_job_keeps_illustration_as_complementary_experience():
    master = load_json("data/cv_master_profile.json")
    job = {
        "title": "Médiateur culturel en bibliothèque",
        "description": "Animation autour du livre, de la lecture et de la création visuelle.",
    }

    plan = analyze_job_for_cv(job, master)
    selected = {item["experience_id"]: item for item in plan["experience_plan"]}

    assert "illustration_neva" in selected
    assert selected["illustration_neva"]["selection_role"] == "complementary"


def test_experience_mix_reserves_one_of_four_slots_for_relevant_journey():
    core_ids = ["core_1", "core_2", "core_3", "core_4"]
    catalog = {
        exp_id: {
            "period": {"start": str(2026 - index), "end": str(2026 - index)},
            "tags": ["culture"],
            "highlights": [exp_id],
        }
        for index, exp_id in enumerate(core_ids)
    }
    catalog["creative"] = {
        "period": {"start": "2022", "end": "2022"},
        "tags": ["culture"],
        "highlights": ["Album jeunesse"],
        "visibility": "only_if_creative",
        "cv_role": "complementary",
    }
    master = {
        "experience_catalog": catalog,
        "adaptation_rules": {"experience_priority_by_variant": {"webmaster": core_ids}},
        "layout_constraints": {"max_experiences": 4},
    }
    selected = {"id": "webmaster", "experience_refs": core_ids}

    plan = _experience_plan({"title": "Culture", "description": ""}, selected, master)

    assert len(plan) == 4
    assert sum(item["selection_role"] == "core" for item in plan) == 3
    assert any(item["experience_id"] == "creative" for item in plan)


def test_ai_plan_can_drop_rule_based_complementary_experience():
    catalog = {
        exp_id: {"period": {"start": "2026", "end": "2026"}, "highlights": [exp_id]}
        for exp_id in ["core_1", "core_2", "core_3", "core_4"]
    }
    catalog["creative"] = {
        "period": {"start": "2022", "end": "2022"},
        "highlights": ["Album jeunesse"],
        "cv_role": "complementary",
    }
    master = {
        "cv_variants": [{"id": "webmaster", "skills": {}}],
        "experience_catalog": catalog,
        "layout_constraints": {"max_experiences": 4},
    }
    rule_plan = {
        "selected_base_variant": "webmaster",
        "experience_plan": [
            *[
                {"experience_id": exp_id, "priority": 10, "selection_role": "core", "highlights": [exp_id]}
                for exp_id in ["core_1", "core_2", "core_3"]
            ],
            {
                "experience_id": "creative",
                "priority": 5,
                "selection_role": "complementary",
                "highlights": ["Album jeunesse"],
            },
        ],
    }
    proposed = {
        "selected_base_variant": "webmaster",
        "experience_plan": [
            {"experience_id": exp_id, "priority": 10, "highlight_indexes": [0]}
            for exp_id in ["core_1", "core_2", "core_3", "core_4"]
        ],
    }

    sanitized = _sanitize_plan(
        proposed,
        rule_plan,
        master,
        AgentResult(data=proposed, provider="test", model="test"),
    )

    ids = [item["experience_id"] for item in sanitized["experience_plan"]]
    assert ids == ["core_1", "core_2", "core_3", "core_4"]


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
    )

    assert review["quality_score"] == 91
    assert review["ats_score"] == 88
    assert review["status"] == "validated"
    assert review["problems"] == []
    assert review["missing_keywords"] == []


def test_generated_cv_keeps_profile_and_skills_quick_to_scan():
    master = load_json("data/cv_master_profile.json")
    job = {
        "title": "Formateur et conseiller numérique",
        "description": "Formation, accompagnement humain, gestion de groupe et outils numériques.",
    }
    plan = analyze_job_for_cv(job, master)
    cv = create_cv_draft(job, master, plan)["cv"]

    assert len(cv["profile"]) <= 240
    assert sum(len(section["items"]) for section in cv["skills"]) <= 10


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


def test_job_application_pipeline_project_is_selected_for_scraping_role():
    master = load_json("data/cv_master_profile.json")
    job = {
        "title": "Développeur Python — automatisation de candidatures",
        "description": "Scraping web, API, analyse d'annonces, génération de CV et lettres de motivation.",
    }
    plan = analyze_job_for_cv(job, master)
    projects = create_cv_draft(job, master, plan)["cv"]["projects"]

    assert [project["id"] for project in projects] == ["job_search_pipeline"]


def test_wordpress_project_remains_selected_for_wordpress_role():
    master = load_json("data/cv_master_profile.json")
    job = {
        "title": "Webmaster WordPress",
        "description": "Administration WordPress, Gutenberg et maintenance de sites.",
    }
    plan = analyze_job_for_cv(job, master)
    draft = create_cv_draft(job, master, plan)
    projects = draft["cv"]["projects"]
    la_magicieuse = next(item for item in draft["cv"]["experiences"] if item["id"] == "la_magicieuse")

    assert [project["id"] for project in projects] == ["wp_site_builder"]
    assert la_magicieuse["links"] == ["https://www.la-magicieuse.org/"]


def test_mediator_trainer_always_uses_devdoc_personal_project():
    master = load_json("data/cv_master_profile.json")
    job = {
        "title": "Médiateur et conseiller numérique",
        "description": "Accompagnement des publics, animation d'ateliers et formation aux usages numériques.",
    }
    plan = analyze_job_for_cv(job, master)
    projects = create_cv_draft(job, master, plan)["cv"]["projects"]

    assert plan["selected_base_variant"] == "formateur_generaliste"
    assert [project["id"] for project in projects] == ["devdoc_platform"]
    assert projects[0]["links"] == ["https://devdoc.varascundo.com/"]


def test_web_cv_always_contains_a_personal_project_without_project_keywords():
    master = load_json("data/cv_master_profile.json")
    job = {
        "title": "Développeur full stack",
        "description": "Conception d'applications PHP Symfony, API REST et backend pour une équipe produit.",
    }
    plan = analyze_job_for_cv(job, master)
    projects = create_cv_draft(job, master, plan)["cv"]["projects"]

    assert plan["selected_base_variant"] == "fullstack"
    assert [project["id"] for project in projects] == ["devdoc_platform"]


def test_unrelated_job_does_not_force_a_personal_project():
    master = load_json("data/cv_master_profile.json")
    job = {
        "title": "Agent de sécurité",
        "description": "Surveillance de nuit et contrôle des accès.",
    }
    plan = analyze_job_for_cv(job, master)
    projects = create_cv_draft(job, master, plan)["cv"]["projects"]

    assert projects == []


def test_backend_trainer_plan_keeps_practice_pedagogy_and_ai_proofs():
    master = load_json("data/cv_master_profile.json")
    job = {
        "title": "Formateur Développement backend MVC",
        "description": (
            "Architecture MVC, bonnes pratiques de code, Bachelor Développement Full Stack, "
            "formateur professionnel en activité sur le développement backend et enseignement supérieur."
        ),
    }

    plan = analyze_job_for_cv(job, master)
    draft = create_cv_draft(job, master, plan)
    ids = {item["experience_id"] for item in plan["experience_plan"]}
    skills = {item for section in draft["cv"]["skills"] for item in section["items"]}

    assert plan["selected_base_variant"] == "formateur_developpement_web"
    assert {
        "pole_s",
        "qualiscope_backend",
        "helene_massage_ayurveda",
        "konexio_formateur_benevole",
        "mairie_chelles",
    } <= ids
    assert "bioconcept_accueil" not in ids
    assert {"PHP 8", "Symfony 6/7", "Doctrine ORM", "ChatGPT", "Claude"} <= skills
    assert [project["id"] for project in draft["cv"]["projects"]] == ["devdoc_platform"]
    assert draft["cv"]["projects"][0]["links"] == ["https://devdoc.varascundo.com/"]


def test_writer_cannot_silently_drop_planned_experiences_or_project():
    master = load_json("data/cv_master_profile.json")
    job = {
        "title": "Formateur Développement backend MVC",
        "description": "Architecture MVC, bonnes pratiques de code et transmission du développement backend.",
    }
    plan = analyze_job_for_cv(job, master)
    base = create_cv_draft(job, master, plan)
    proposed = {
        "title": "Formateur backend",
        "profile": "Formateur et développeur backend.",
        "skills": [{"title": "Backend", "items": ["PHP 8", "Symfony 6/7"]}],
        "experiences": [],
        "projects": [],
    }

    sanitized = _sanitize_cv_content(
        proposed,
        job,
        master,
        plan,
        base,
        AgentResult(data=proposed, provider="test", model="test"),
        "test_writer",
    )

    assert sanitized["cv"]["experiences"] == []
    assert sanitized["cv"]["projects"] == []
    skills = {item for section in sanitized["cv"]["skills"] for item in section["items"]}
    assert skills == {"PHP 8", "Symfony 6/7"}


def test_reviser_can_apply_grounded_order_education_and_project_reduction():
    master = load_json("data/cv_master_profile.json")
    job = {
        "title": "Formateur Développement backend MVC",
        "description": "Architecture MVC, PHP Symfony, JavaScript et transmission du développement web.",
    }
    plan = analyze_job_for_cv(job, master)
    base = create_cv_draft(job, master, plan)
    reversed_ids = [item["experience_id"] for item in reversed(plan["experience_plan"])]
    proposed = {
        "title": "Formateur Développement backend MVC",
        "profile": "Formateur et développeur web, orienté transmission et autonomie.",
        "skills": [{"title": "Technique", "items": ["PHP 8", "JavaScript ES6+"]}],
        "experiences": [
            {
                "id": exp_id,
                "bullets": [{"text": master["experience_catalog"][exp_id]["highlights"][0], "source_highlight_indexes": [0]}],
            }
            for exp_id in reversed_ids
        ],
        "projects": [{
            "id": "devdoc_platform",
            "description": "Plateforme pédagogique de cours, exercices et QCM.",
            "technologies": ["Symfony 6.4", "Vue.js 3"],
        }],
        "education": ["CAP Petite Enfance"],
    }

    sanitized = _sanitize_cv_content(
        proposed,
        job,
        master,
        plan,
        base,
        AgentResult(data=proposed, provider="test", model="test"),
        "test_reviser",
    )

    assert [item["id"] for item in sanitized["cv"]["experiences"]] == reversed_ids
    assert sanitized["cv"]["projects"][0]["technologies"] == ["Symfony 6.4", "Vue.js 3"]
    education_titles = [item["title"] for item in sanitized["cv"]["education"]]
    assert education_titles == ["CAP Petite Enfance"]


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


def test_experience_plan_is_reverse_chronological_after_selection():
    ids = ["freelance", "current", "qualiscope", "pole_s"]
    periods = {
        "freelance": {"start": "2023", "end": "2024"},
        "current": {"start": "2026-06", "end": None},
        "qualiscope": {"start": "2026-03", "end": "2026-08"},
        "pole_s": {"start": "2024-12", "end": "2026-03"},
    }
    master = {
        "experience_catalog": {
            exp_id: {"period": periods[exp_id], "tags": [], "highlights": [exp_id]}
            for exp_id in ids
        },
        "adaptation_rules": {"experience_priority_by_variant": {"webmaster": ids}},
        "layout_constraints": {"max_experiences": 4},
    }
    selected = {"id": "webmaster", "experience_refs": ids}

    plan = _experience_plan({}, selected, master)

    assert [item["experience_id"] for item in plan] == ["current", "qualiscope", "pole_s", "freelance"]


def test_conditional_experience_is_selected_only_when_job_tags_match():
    master = {
        "experience_catalog": {
            "web": {
                "period": {"start": "2024", "end": None},
                "tags": ["developpement web"],
                "highlights": ["Développement d'applications web"],
                "visibility": "default",
            },
            "logistics": {
                "period": {"start": "2018", "end": "2021"},
                "tags": ["logistique", "preparation de commandes"],
                "highlights": ["Préparation de commandes"],
                "visibility": "only_if_relevant",
            },
        },
        "adaptation_rules": {"experience_priority_by_variant": {"webmaster": ["web"]}},
        "layout_constraints": {"max_experiences": 4},
    }
    selected = {"id": "webmaster", "experience_refs": ["web"]}

    web_plan = _experience_plan(
        {"title": "Développeur web", "description": "Maintenance de sites"},
        selected,
        master,
    )
    logistics_plan = _experience_plan(
        {"title": "Préparateur logistique", "description": "Préparation de commandes"},
        selected,
        master,
    )

    assert [item["experience_id"] for item in web_plan] == ["web"]
    assert [item["experience_id"] for item in logistics_plan] == ["web", "logistics"]


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
