from cv_generator import prepare_custom_cv
from cv_generator.ai_agents import AgentResult
from cv_generator.exporters import DEFAULT_PORTRAIT, cv_to_html, cv_to_pdf
from cv_generator.job_analyzer import _experience_plan


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
    assert result["pipeline"] == "ai_cv_pipeline_v2"
    assert result["selected_base_variant"] == "webmaster"
    assert "Webmaster" in result["target_title"]
    assert client.calls == [
        "cv_job_analyzer",
        "cv_creator",
        "cv_quality_checker",
        "cv_style_reviser",
        "cv_quality_checker",
    ]
    assert (tmp_path / "cv" / "cv_final.json").exists()
    assert (tmp_path / "cv" / "cv_agent_trace.json").exists()
    assert (tmp_path / "cv" / "cv_canva_copy.md").exists()
    assert (tmp_path / "cv" / "cv_final.html").exists()
    assert (tmp_path / "cv" / "cv_final.pdf").exists()
    assert (tmp_path / "cv" / "cv_final.pdf").read_bytes().startswith(b"%PDF")
    canva = (tmp_path / "cv" / "cv_canva_copy.md").read_text(encoding="utf-8")
    assert "WordPress" in canva
    assert "Facundo Varas" in canva


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

    pdf_path = tmp_path / "cv.pdf"
    cv_to_pdf(final_cv, pdf_path)
    assert pdf_path.read_bytes().startswith(b"%PDF")
    assert pdf_path.stat().st_size > 10_000


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
