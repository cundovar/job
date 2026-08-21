from agents import summarize_job


def test_summarize_job_detects_interesting_points_and_postuler_action():
    job = {
        "title": "Webmaster institutionnel WordPress",
        "company": "Ville Test",
        "location": "Paris",
        "description": "CMS WordPress, accessibilite RGAA, documentation et service public.",
        "score": 86,
    }

    summary = summarize_job(job)

    assert summary.action == "POSTULER"
    assert any("CMS" in point or "Webmaster" in point for point in summary.why_interesting)
    assert any("public" in point.lower() or "WordPress" in point for point in summary.why_interesting)
    assert summary.risks == []


def test_summarize_job_detects_risks_and_maybe_action():
    job = {
        "title": "Developpeur fullstack senior",
        "company": "Tech Test",
        "location": "Remote",
        "description": "Profil expert avec minimum 5 ans, devops Kubernetes et prospection.",
        "score": 62,
    }

    summary = summarize_job(job)

    assert summary.action == "PEUT-ÊTRE"
    assert any("senior" in risk for risk in summary.risks)
    assert any("commerciale" in risk for risk in summary.risks)


def test_summarize_job_uses_ai_recommendation_when_available():
    job = {
        "title": "Support applicatif",
        "company": "Asso Test",
        "description": "Support fonctionnel et documentation.",
        "score": 40,
        "ai_analysis": {
            "recommandation": "POSTULER",
            "points_forts": ["Tres bon alignement support"],
            "red_flags": ["Contrat court"],
        },
    }

    summary = summarize_job(job)

    assert summary.action == "POSTULER"
    assert "Tres bon alignement support" in summary.why_interesting
    assert "Contrat court" in summary.risks
