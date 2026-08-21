import json

from hermes_commands.utils import format_job_list, get_job_by_number, load_cached_jobs, ranked_jobs


def test_load_cached_jobs_returns_empty_list_for_missing_file(tmp_path):
    assert load_cached_jobs(str(tmp_path / "missing.json")) == []


def test_ranked_jobs_sorts_by_score_desc():
    jobs = [
        {"title": "Low", "score": 20},
        {"title": "High", "score": 90},
        {"title": "Mid", "score": 50},
    ]

    ranked = ranked_jobs(jobs, limit=2)

    assert [job["title"] for job in ranked] == ["High", "Mid"]


def test_get_job_by_number_is_one_based():
    jobs = [{"title": "First"}, {"title": "Second"}]

    assert get_job_by_number(jobs, 2)["title"] == "Second"


def test_format_job_list_includes_cv_and_action(tmp_path):
    cache = tmp_path / "jobs.json"
    cache.write_text(
        json.dumps(
            [
                {
                    "title": "Webmaster WordPress",
                    "company": "Ville Test",
                    "location": "Paris",
                    "description": "CMS WordPress accessibilite RGAA service public",
                    "score": 86,
                    "url": "https://example.com",
                }
            ]
        ),
        encoding="utf-8",
    )

    output = format_job_list(load_cached_jobs(str(cache)), title="Top test")

    assert "Webmaster WordPress" in output
    assert "Action : POSTULER" in output
    assert "CV conseille : Webmaster / Administrateur de Sites Web" in output
