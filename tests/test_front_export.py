import json

import front_export


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
