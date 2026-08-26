from applications import recommend_cv


def test_recommend_webmaster_cv_for_cms_job():
    job = {
        "title": "Webmaster institutionnel WordPress",
        "description": "Gestion de contenu, accessibilite RGAA et site institutionnel.",
    }
    recommendation = recommend_cv(job)
    assert recommendation.cv_id == "webmaster"
    assert recommendation.score >= 3
    assert any("wordpress" in kw or "webmaster" in kw for kw in recommendation.matched_keywords)


def test_recommend_fullstack_variant_for_symfony_job():
    job = {
        "title": "Développeur Symfony / React",
        "description": "PHP 8, Symfony 7, API REST, architecture back-end.",
    }
    recommendation = recommend_cv(job)
    assert recommendation.cv_id == "fullstack"
    assert recommendation.score >= 3
    assert any(kw in recommendation.matched_keywords for kw in ["symfony", "php"])


def test_recommend_fullstack_variant_for_frontend_job():
    job = {
        "title": "Developpeur frontend React",
        "description": "Integration web HTML CSS JavaScript Vue.",
    }
    recommendation = recommend_cv(job)
    assert recommendation.cv_id == "fullstack"
    assert recommendation.score >= 3
    assert "react" in recommendation.matched_keywords


def test_recommend_formateur_web_variant_for_training_job():
    job = {
        "title": "Formateur web et développement",
        "description": "Formation adultes, ateliers numeriques, pedagogie et mentorat.",
    }
    recommendation = recommend_cv(job)
    assert recommendation.cv_id == "formateur_developpement_web"
    assert recommendation.score >= 3
    assert "formation" in recommendation.matched_keywords


def test_recommend_formateur_ia_cv_for_ia_job():
    job = {
        "title": "Formateur IA générative",
        "description": "ChatGPT, Claude, prompt engineering, ateliers IA.",
    }
    recommendation = recommend_cv(job)
    assert recommendation.cv_id == "formateur_ia"
    assert recommendation.score >= 2
    assert any(kw in recommendation.matched_keywords for kw in ["ia", "prompt"])


def test_recommendation_has_no_file_path():
    """Les variantes viennent du master profile : plus aucun PDF a pointer."""
    recommendation = recommend_cv({"title": "Webmaster", "description": "wordpress"})
    assert not hasattr(recommendation, "cv_path")
