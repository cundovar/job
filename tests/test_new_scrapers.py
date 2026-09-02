from scrapers import AdzunaScraper, JoobleScraper, RemoteOKScraper


def test_adzuna_retries_temporary_server_error(monkeypatch):
    responses = []

    class Response:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self._payload = payload or {}

        def json(self):
            return self._payload

    responses.extend([
        Response(503),
        Response(200, {"results": [{"title": "Développeur PHP", "redirect_url": "https://job.test/1"}]}),
        Response(200, {"results": []}),
    ])
    monkeypatch.setenv("ADZUNA_APP_ID", "id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "secret")
    monkeypatch.setenv("ADZUNA_MAX_RETRIES", "3")
    monkeypatch.setenv("ADZUNA_RETRY_BACKOFF_SECONDS", "0")
    monkeypatch.setenv("MAX_JOBS_PER_SITE", "10")
    monkeypatch.setattr("scrapers.adzuna_scraper.requests.get", lambda *args, **kwargs: responses.pop(0))

    jobs = AdzunaScraper().scrape(["php"])

    assert [job["title"] for job in jobs] == ["Développeur PHP"]


def test_adzuna_error_does_not_leak_credentials(monkeypatch):
    class Response:
        status_code = 503

    monkeypatch.setenv("ADZUNA_APP_ID", "sensitive-id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "sensitive-key")
    monkeypatch.setenv("ADZUNA_MAX_RETRIES", "1")
    monkeypatch.setattr("scrapers.adzuna_scraper.requests.get", lambda *args, **kwargs: Response())

    try:
        AdzunaScraper()._search("php", 1)
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("Une erreur Adzuna etait attendue")

    assert message == "Adzuna API HTTP 503"
    assert "sensitive" not in message


def test_remoteok_scraper_parses_matching_jobs(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {"legal": "terms"},
                {
                    "position": "Remote Support Applicatif",
                    "company": "Remote Co",
                    "location": "Remote",
                    "description": "Support applicatif et documentation",
                    "tags": ["support"],
                    "url": "https://remoteok.com/job",
                    "salary_min": 30000,
                    "salary_max": 40000,
                },
                {
                    "position": "Sales Manager",
                    "company": "Sales Co",
                    "description": "Commercial",
                    "tags": ["sales"],
                    "url": "https://remoteok.com/sales",
                },
            ]

    monkeypatch.setattr("scrapers.remoteok_scraper.requests.get", lambda *args, **kwargs: Response())

    jobs = RemoteOKScraper(max_jobs=10).scrape(["support applicatif"])

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Remote Support Applicatif"
    assert jobs[0]["source"] == "remoteok"
    assert jobs[0]["salary"] == "30000 - 40000"


def test_jooble_scraper_parses_jobs(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "jobs": [
                    {
                        "title": "Webmaster WordPress",
                        "company": "Ville Test",
                        "location": "Paris",
                        "type": "CDI",
                        "salary": "35k",
                        "snippet": "Gestion CMS WordPress",
                        "link": "https://jooble.org/job",
                    }
                ]
            }

    monkeypatch.setattr("scrapers.jooble_scraper.requests.post", lambda *args, **kwargs: Response())

    jobs = JoobleScraper(api_key="test-key", max_jobs=10).scrape(["webmaster"])

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Webmaster WordPress"
    assert jobs[0]["source"] == "jooble"
    assert jobs[0]["url"] == "https://jooble.org/job"
