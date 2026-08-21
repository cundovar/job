from scrapers import JoobleScraper, RemoteOKScraper


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
