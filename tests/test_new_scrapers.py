from scrapers import (
    APECScraper,
    AdzunaScraper,
    EmploiESSScraper,
    EmploiTerritorialRssScraper,
    FranceTravailScraper,
    JoobleScraper,
    LesJeudisScraper,
    RemoteOKScraper,
)
from scrapers.base_scraper import balanced_keyword_limits


def test_balanced_keyword_limits_distributes_capacity_across_keywords():
    assert balanced_keyword_limits(
        ["symfony", "react", "wordpress", "n8n"],
        max_jobs=10,
        max_keywords=3,
    ) == [("symfony", 4), ("react", 3), ("wordpress", 3)]


def test_apec_uses_current_api_contract_and_result_fields(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultats": [
                    {
                        "intitule": "Chef de projet numérique",
                        "nomCommercial": "Association Exemple",
                        "lieuTexte": "Paris 01 - 75",
                        "typeContrat": "CDI",
                        "salaireTexte": "40 k€",
                        "texteOffre": "Pilotage, formation et assistance utilisateurs",
                        "numeroOffre": "123456",
                        "datePublication": "2026-09-03T08:00:00Z",
                    }
                ]
            }

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.delenv("APEC_LOCATION_IDS", raising=False)
    scraper = APECScraper()
    monkeypatch.setattr(scraper.session, "post", fake_post)

    raw = scraper._search("chef de projet numérique")[0]
    job = scraper._parse_job(raw)

    assert captured["json"]["lieux"] == [711]
    assert captured["json"]["sorts"] == [
        {"type": "DATE", "direction": "DESCENDING"}
    ]
    assert "sortsAndFilters" not in captured["json"]
    assert job["company"] == "Association Exemple"
    assert job["location"] == "Paris 01 - 75"
    assert job["salary"] == "40 k€"
    assert job["description"].startswith("Pilotage")
    assert job["published_at"] == "2026-09-03T08:00:00Z"


def test_emploi_ess_uses_current_query_and_markup(monkeypatch):
    captured = {}
    html = """
    <div class="bloc-offre fondoffre">
      <div class="offre-localisation">localisation :
        <span class="text-bleu-light">Île-de-France</span>
      </div>
      <div class="offre-date">03/09/2026</div>
      <div class="offre-titre">
        <a href="https://www.emploi-ess.fr/jobs/3572898/270">
          Chef de projet numérique Objectif Terres F/H
        </a>
      </div>
      <div class="offre-descriptif">Type de contrat : CDI. Pilotage digital et formation.</div>
    </div>
    """

    class Response:
        text = html

        def raise_for_status(self):
            return None

    def fake_get(url, **kwargs):
        captured.update(kwargs)
        return Response()

    scraper = EmploiESSScraper()
    monkeypatch.setattr(scraper.session, "get", fake_get)

    jobs = scraper.scrape(["numérique"])

    assert captured["params"] == {"m": "numérique"}
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Chef de projet numérique Objectif Terres F/H"
    assert jobs[0]["location"] == "Île-de-France"
    assert jobs[0]["contract_type"] == "CDI"
    assert jobs[0]["published_at"] == "2026-09-03"
    assert jobs[0]["url"] == "https://www.emploi-ess.fr/jobs/3572898/270"


def test_france_travail_shares_its_limit_between_keywords(monkeypatch):
    monkeypatch.setenv("FRANCE_TRAVAIL_CLIENT_ID", "id")
    monkeypatch.setenv("FRANCE_TRAVAIL_CLIENT_SECRET", "secret")
    monkeypatch.setenv("MAX_JOBS_PER_SITE", "4")
    monkeypatch.setenv("MAX_KEYWORDS_PER_SOURCE", "2")
    scraper = FranceTravailScraper()

    def fake_search(keyword):
        return {
            "resultats": [
                {
                    "id": f"{keyword}-{index}",
                    "intitule": f"{keyword} offre {index}",
                }
                for index in range(4)
            ]
        }

    monkeypatch.setattr(scraper, "_search", fake_search)

    jobs = scraper.scrape(["symfony", "react"])

    assert len(jobs) == 4
    assert sum("symfony" in job["title"] for job in jobs) == 2
    assert sum("react" in job["title"] for job in jobs) == 2


def test_adzuna_shares_its_limit_between_keywords(monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "secret")
    monkeypatch.setenv("MAX_JOBS_PER_SITE", "4")
    monkeypatch.setenv("MAX_KEYWORDS_PER_SOURCE", "2")
    scraper = AdzunaScraper()

    def fake_search(keyword, page):
        if page > 1:
            return {"results": []}
        return {
            "results": [
                {
                    "title": f"{keyword} offre {index}",
                    "redirect_url": f"https://jobs.test/{keyword}/{index}",
                }
                for index in range(4)
            ]
        }

    monkeypatch.setattr(scraper, "_search", fake_search)

    jobs = scraper.scrape(["symfony", "react"])

    assert len(jobs) == 4
    assert sum("symfony" in job["title"] for job in jobs) == 2
    assert sum("react" in job["title"] for job in jobs) == 2


def test_lesjeudis_shares_its_limit_between_keywords(monkeypatch):
    monkeypatch.setenv("MAX_JOBS_PER_SITE", "4")
    monkeypatch.setenv("MAX_KEYWORDS_PER_SOURCE", "2")
    scraper = LesJeudisScraper()

    def fake_search(keyword):
        cards = "".join(
            f'<div><a href="/fr/job/{keyword}-{index}">{keyword} offre {index}</a></div>'
            for index in range(4)
        )
        return f'<div id="jobs">{cards}</div>'

    monkeypatch.setattr(scraper, "_search", fake_search)

    jobs = scraper.scrape(["symfony", "react"])

    assert len(jobs) == 4
    assert sum("symfony" in job["title"] for job in jobs) == 2
    assert sum("react" in job["title"] for job in jobs) == 2


def test_emploi_territorial_uses_public_feed_by_default(monkeypatch):
    monkeypatch.delenv("EMPLOI_TERRITORIAL_RSS_URLS", raising=False)
    monkeypatch.delenv("EMPLOI_TERRITORIAL_RSS_URL", raising=False)

    scraper = EmploiTerritorialRssScraper()

    assert scraper.rss_urls == ["https://www.emploi-territorial.fr/rss/"]


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
