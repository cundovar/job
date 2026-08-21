from datetime import date

from applications import ApplicationTracker, build_application_package


def test_tracker_marks_ready_and_applied(tmp_path):
    tracker = ApplicationTracker(str(tmp_path / "tracker.json"))
    job = {
        "title": "Webmaster WordPress",
        "company": "Ville Test",
        "description": "CMS WordPress accessibilite RGAA",
        "url": "https://example.com/job",
        "score": 86,
    }
    package = build_application_package(job, output_dir=str(tmp_path / "applications"))

    ready = tracker.mark_ready(job, package)
    applied = tracker.mark_applied(job, follow_up_days=0, notes="Candidature envoyee")

    assert ready["status"] == "ready_to_apply"
    assert applied["status"] == "applied"
    assert applied["notes"] == "Candidature envoyee"
    assert applied["follow_up_at"] == date.today().isoformat()
    assert tracker.due_followups(today=date.today())[0]["job_title"] == "Webmaster WordPress"


def test_tracker_ignores_future_followups(tmp_path):
    tracker = ApplicationTracker(str(tmp_path / "tracker.json"))
    job = {
        "title": "Support applicatif",
        "company": "Asso Test",
        "description": "Support applicatif SQL ERP documentation",
        "url": "https://example.com/support",
    }

    tracker.mark_applied(job, follow_up_days=7)

    assert tracker.due_followups(today=date.today()) == []
