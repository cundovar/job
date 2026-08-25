import json
from pathlib import Path

import pytest

from cv_generator.cv_assessment import (
    CVAssessmentConfigError,
    build_cv_assessment,
    load_assessment_config,
    validate_assessment_config,
)
from cv_generator.job_analyzer import _experience_plan


FIXTURES = Path(__file__).parent / "fixtures" / "cv_assessment_cases.json"


def _master():
    return {
        "person": {
            "eligibility": {
                "work_authorization": {"value": True, "evidence": "Autorisation confirmée"},
                "driver_license": {"value": None},
            }
        },
        "skills_confidence": {"PHP": "pratique", "Symfony": "pratique"},
        "experience_catalog": {
            "backend": {
                "organization": "Example",
                "title": "Développeur back-end",
                "highlights": ["Développement Symfony"],
            }
        },
        "cv_variants": [{"id": "backend", "skills": {"backend": ["PHP", "Symfony"]}}],
        "forbidden_claims": ["expert cybersécurité"],
        "layout_constraints": {"max_profile_chars": 420, "max_bullet_chars": 145, "max_experiences": 4},
    }


def _plan():
    return {
        "priority_keywords": ["PHP", "Symfony"],
        "experience_plan": [{"experience_id": "backend"}],
    }


def _cv():
    return {
        "cv": {
            "title": "Développeur PHP Symfony",
            "profile": "Développeur web spécialisé en PHP et Symfony pour des applications métier fiables.",
            "skills": [{"title": "Back-end", "items": ["PHP", "Symfony"]}],
            "experiences": [
                {
                    "id": "backend",
                    "organization": "Example",
                    "title": "Développeur back-end",
                    "bullets": ["Développement Symfony"],
                }
            ],
            "education": [],
        },
        "grounding": {"experience_bullets": [{"experience_id": "backend"}]},
    }


def test_default_weights_total_one_hundred():
    config = load_assessment_config()
    assert sum(config["match_weights"].values()) == 100
    assert sum(config["human_quality_weights"].values()) == 100


def test_invalid_weights_fail_explicitly():
    with pytest.raises(CVAssessmentConfigError, match="totaliser 100"):
        validate_assessment_config(
            {
                "match_weights": {"skills": 90},
                "human_quality_weights": {"quality": 100},
            }
        )


def test_assessment_is_grounded_and_ready_when_all_controls_pass(tmp_path):
    assessment = build_cv_assessment(
        {
            "title": "Développeur PHP Symfony",
            "description": "PHP et Symfony. Autorisation de travail requise.",
        },
        _master(),
        _plan(),
        _cv(),
        parseability={"status": "pass", "missing": [], "reason": "PDF lisible"},
    )

    assert assessment["schema_version"] == "cv_assessment_v1"
    assert assessment["eligibility"]["status"] == "pass"
    assert assessment["truthfulness"]["status"] == "pass"
    assert assessment["match"]["score"] >= 85
    assert assessment["overall_status"] == "ready"
    json.dumps(assessment)


def test_unknown_hard_requirement_requires_review_not_failure():
    assessment = build_cv_assessment(
        {
            "title": "Développeur PHP",
            "description": "PHP. Permis B obligatoire.",
        },
        _master(),
        _plan(),
        _cv(),
        parseability={"status": "pass", "missing": [], "reason": "PDF lisible"},
    )

    assert assessment["eligibility"]["status"] == "review"
    assert assessment["overall_status"] == "review"


def test_unknown_skill_blocks_truthfulness():
    cv = _cv()
    cv["cv"]["skills"][0]["items"].append("Kubernetes")
    assessment = build_cv_assessment(
        {"title": "Développeur PHP", "description": "PHP"},
        _master(),
        _plan(),
        cv,
        parseability={"status": "pass", "missing": [], "reason": "PDF lisible"},
    )

    assert assessment["truthfulness"]["status"] == "fail"
    assert assessment["overall_status"] == "blocked"


def test_assessment_is_stable_for_identical_evidence():
    args = (
        {"title": "Développeur PHP Symfony", "description": "PHP Symfony"},
        _master(),
        _plan(),
        _cv(),
    )
    parsing = {"status": "pass", "missing": [], "reason": "PDF lisible"}

    first = build_cv_assessment(*args, parseability=parsing)
    second = build_cv_assessment(*args, parseability=parsing)

    assert first == second


@pytest.mark.parametrize("case", json.loads(FIXTURES.read_text(encoding="utf-8")), ids=lambda item: item["id"])
def test_conditional_experience_golden_cases(case):
    catalog = {
        "web": {
            "period": {"start": "2024", "end": None},
            "tags": ["wordpress", "symfony", "developpement web"],
            "highlights": ["Développement et maintenance web"],
            "visibility": "default",
        },
        "training": {
            "period": {"start": "2022", "end": None},
            "tags": ["formateur web", "formation", "html", "javascript"],
            "highlights": ["Formation HTML CSS JavaScript"],
            "visibility": "only_if_relevant",
        },
        "accueil": {
            "period": {"start": "2024-07", "end": "2025-12"},
            "tags": ["gardien", "hote d'accueil", "accueil", "gestion de site", "locataires"],
            "highlights": ["Accueil des locataires et gestion de site"],
            "visibility": "only_if_relevant",
        },
        "logistics": {
            "period": {"start": "2018", "end": "2021"},
            "tags": ["logistique", "preparation de commandes", "conditionnement"],
            "highlights": ["Préparation de commandes et conditionnement"],
            "visibility": "only_if_relevant",
        },
        "animation": {
            "period": {"start": "2013", "end": "2018"},
            "tags": ["animateur periscolaire", "centre de loisirs", "enfants", "projets pedagogiques"],
            "highlights": ["Animation en centre de loisirs"],
            "visibility": "only_if_relevant",
        },
    }
    master = {
        "experience_catalog": catalog,
        "adaptation_rules": {"experience_priority_by_variant": {"webmaster": ["web"]}},
        "layout_constraints": {"max_experiences": 5},
    }
    selected = {"id": "webmaster", "experience_refs": ["web"]}

    plan = _experience_plan(
        {"title": case["title"], "description": case["description"]},
        selected,
        master,
    )
    selected_ids = {item["experience_id"] for item in plan}

    assert set(case["expected_conditional"]).issubset(selected_ids)
    assert set(case["forbidden_conditional"]).isdisjoint(selected_ids)
