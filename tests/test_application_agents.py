from agents import generate_application_email, generate_motivation_letter
from applications import recommend_cv


def test_generate_motivation_letter_uses_job_cv_and_profile():
    job = {
        "title": "Webmaster institutionnel WordPress",
        "company": "Ville Test",
        "description": "CMS WordPress, accessibilite RGAA, documentation et service public.",
        "score": 86,
        "ai_analysis": {"angle_motivation": "Insister sur CMS, qualite web et support utilisateurs."},
    }
    recommendation = recommend_cv(job)
    profile = {
        "name": "Facundo Varas (Cundo)",
        "core_strengths": ["Développeur full-stack freelance PHP/Symfony", "Formateur développement web"],
        "experiences": [
            "Le Pôle S (2022-2025) : Encadrant Technique Développeur — formateur web full-stack",
            "DevDoc (varascundo.com) : plateforme pédagogique Vue.js, 15+ technos",
        ],
    }

    letter = generate_motivation_letter(job, recommendation, profile)

    assert "Webmaster institutionnel WordPress" in letter
    assert "Ville Test" in letter
    assert "Pôle S" in letter  # experience should appear
    assert recommendation.cv_name in letter


def test_generate_application_email_mentions_cv_to_attach():
    job = {
        "title": "Administrateur applicatif",
        "company": "Association Exemple",
        "description": "Support applicatif, SQL, ERP et documentation.",
    }
    recommendation = recommend_cv(job)

    email = generate_application_email(job, recommendation, {"name": "Facundo Varas (Cundo)"})

    assert "Candidature" in email and "Administrateur applicatif" in email
    assert "Association Exemple" in email
    assert recommendation.cv_name in email
    assert "Facundo Varas" in email
