import json

import front_export
import pytest


def _job(title, url, recommendation, score=80, description=""):
    return {
        "title": title,
        "company": "Entreprise test",
        "location": "Paris",
        "contract_type": "CDI",
        "description": description or title,
        "salary": "35 k€",
        "sector": "Numérique",
        "source": "test",
        "score": score,
        "scraped_at": "2026-08-24T12:00:00Z",
        "url": url,
        "ai_analysis": {
            "recommandation": recommendation,
            "points_forts": ["Point 1", "Point 2"],
            "points_faibles": [],
        },
    }


def test_export_accumulates_runs_from_the_same_day(tmp_path, monkeypatch):
    monkeypatch.setattr(front_export, "FRONT_DATA_DIR", tmp_path)

    front_export.export_front_data(
        [
            _job(
                "Développeur API Symfony",
                "https://example.test/backend",
                "POSTULER",
                description="PHP Symfony et développement backend",
            ),
            _job(
                "Intégrateur React",
                "https://example.test/frontend",
                "PEUT-ÊTRE",
                description="React JavaScript et intégration frontend",
            ),
        ],
        "2026-08-24",
    )
    front_export.export_front_data(
        [
            _job(
                "Formateur WordPress",
                "https://example.test/formateur",
                "POSTULER",
                description="Formation et pédagogie WordPress",
            )
        ],
        "2026-08-24",
    )

    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    search = index["searches"][0]
    assert search["total"] == 3
    assert search["postuler"] == 2
    assert search["peut_etre"] == 1
    assert search["categories"] == {
        "backend": {"count": 1},
        "frontend": {"count": 1},
        "webmaster_formateur": {"count": 1},
    }


def test_export_updates_duplicate_without_hiding_other_results(tmp_path, monkeypatch):
    monkeypatch.setattr(front_export, "FRONT_DATA_DIR", tmp_path)
    original = _job("Développeur API", "https://example.test/job", "PEUT-ÊTRE", score=60)
    other = _job("Formateur web", "https://example.test/other", "POSTULER", score=75)
    front_export.export_front_data([original, other], "2026-08-24")

    updated = _job("Développeur API confirmé", "https://example.test/job", "POSTULER", score=95)
    front_export.export_front_data([updated], "2026-08-24")

    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert index["searches"][0]["total"] == 2
    backend = json.loads(
        (tmp_path / "2026-08-24" / "backend.json").read_text(encoding="utf-8")
    )
    assert [job["title"] for job in backend["jobs"]] == ["Développeur API confirmé"]
    assert backend["jobs"][0]["description"] == "Développeur API confirmé"


@pytest.mark.parametrize(
    ("title", "description", "expected"),
    [
        ("AI & Ops Automation", "Workflows n8n, agents IA et webhooks", "nouvelles_portes"),
        ("AI Automation Engineer", "Notion, OpenAI et APIs internes", "nouvelles_portes"),
        ("Chef de projets IT, solutions Low Code & IA", "Power Automate et Copilot Studio", "nouvelles_portes"),
        ("Développeur No-code / IA – Chatbots", "Automatisation et assistants IA", "nouvelles_portes"),
        ("Consultant IA", "Prompt Engineering, Claude Code et n8n", "nouvelles_portes"),
        ("Lead Développeur Réact.js", "Applications web", "frontend"),
        ("Développeur Full-Stack", "Développement logiciel", "backend"),
        ("Responsable opérations", "Gestion quotidienne", "non_classees"),
    ],
)
def test_categorize_automation_and_generic_developer_roles(title, description, expected):
    assert front_export._categorize({"title": title, "description": description}) == expected


def test_export_separates_jobs_seen_on_a_previous_day(tmp_path, monkeypatch):
    monkeypatch.setattr(front_export, "FRONT_DATA_DIR", tmp_path)

    repeated = _job("Développeur Symfony", "https://example.test/job?utm_source=old", "POSTULER")
    front_export.export_front_data([repeated], "2026-08-25")

    repeated_with_tracking = _job(
        "Développeur Symfony",
        "https://example.test/job?utm_source=new",
        "POSTULER",
    )
    automation = _job(
        "AI & Ops Automation",
        "https://example.test/automation",
        "POSTULER",
        description="Workflows n8n, agents IA, API REST et webhooks",
    )
    front_export.export_front_data([repeated_with_tracking, automation], "2026-08-26")

    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    current = index["searches"][0]
    assert current["total"] == 1
    assert current["already_seen"] == 1
    assert current["categories"] == {
        "nouvelles_portes": {"count": 1},
        "deja_vues": {"count": 1},
    }

    new_jobs = json.loads(
        (tmp_path / "2026-08-26" / "nouvelles_portes.json").read_text(encoding="utf-8")
    )["jobs"]
    seen_jobs = json.loads(
        (tmp_path / "2026-08-26" / "deja_vues.json").read_text(encoding="utf-8")
    )["jobs"]
    assert [job["title"] for job in new_jobs] == ["AI & Ops Automation"]
    assert [job["title"] for job in seen_jobs] == ["Développeur Symfony"]


def test_export_deduplicates_the_same_role_across_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(front_export, "FRONT_DATA_DIR", tmp_path)
    first = _job("AI Automation Engineer", "https://source-a.test/123", "POSTULER")
    first["company"] = "Lydia Solutions"
    front_export.export_front_data([first], "2026-08-25")

    second = _job("AI Automation Engineer", "https://source-b.test/jobs/456", "POSTULER")
    second["company"] = "Lydia Solutions"
    front_export.export_front_data([second], "2026-08-26")

    seen_jobs = json.loads(
        (tmp_path / "2026-08-26" / "deja_vues.json").read_text(encoding="utf-8")
    )["jobs"]
    assert [job["title"] for job in seen_jobs] == ["AI Automation Engineer"]


def test_export_preserves_the_source_publication_date(tmp_path, monkeypatch):
    monkeypatch.setattr(front_export, "FRONT_DATA_DIR", tmp_path)
    job = _job("AI Automation Engineer", "https://example.test/dated", "POSTULER")
    job["published_at"] = "2026-08-20T09:00:00Z"

    front_export.export_front_data([job], "2026-08-26")

    exported = json.loads(
        (tmp_path / "2026-08-26" / "nouvelles_portes.json").read_text(encoding="utf-8")
    )["jobs"][0]
    assert exported["published_at"] == "2026-08-20T09:00:00Z"
    assert exported["scraped_at"] == "2026-08-24T12:00:00Z"
