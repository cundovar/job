import json

import pytest

from cv_generator.cv_assessment import (
    CVAssessmentConfigError,
    build_cv_assessment,
    load_assessment_config,
    validate_assessment_config,
)


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
