from storage.json_storage import JSONStorage


def test_sent_jobs_are_not_returned_the_next_day(tmp_path):
    storage = JSONStorage(
        path=str(tmp_path / "jobs_cache.json"),
        sent_path=str(tmp_path / "sent_jobs.json"),
        cache_days=30,
    )

    jobs = [
        {
            "title": "Webmaster WordPress",
            "company": "Ville de Paris",
            "url": "https://example.com/job-1",
        },
        {
            "title": "Formateur developpement web et IA",
            "company": "Ecole Numerique",
            "url": "https://example.com/job-2",
        },
    ]

    assert storage.get_unsent_jobs(jobs) == jobs

    storage.mark_jobs_as_sent([jobs[0]])

    assert storage.get_unsent_jobs(jobs) == [jobs[1]]
