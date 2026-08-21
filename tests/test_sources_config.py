from pipeline import build_scrapers, load_sources
from scrapers import JoobleScraper, RemoteOKScraper


def test_build_scrapers_keeps_optional_sources_disabled_by_default():
    scrapers = build_scrapers(
        {
            "enabled_sources": {
                "france_travail": False,
                "adzuna": False,
                "emploi_territorial": False,
                "apec": False,
                "indeed": False,
                "wttj": False,
                "emploi_asso": False,
                "emploi_ess": False,
                "lesjeudis": False,
                "jooble": False,
                "remoteok": False,
            }
        }
    )

    assert scrapers == []


def test_build_scrapers_can_enable_new_sources():
    scrapers = build_scrapers(
        {
            "enabled_sources": {
                "france_travail": False,
                "adzuna": False,
                "emploi_territorial": False,
                "jooble": True,
                "remoteok": True,
            },
            "jooble": {"country": "fr", "location": "Paris", "max_jobs": 3},
            "remoteok": {"max_jobs": 4},
        }
    )

    assert any(isinstance(scraper, JoobleScraper) for scraper in scrapers)
    assert any(isinstance(scraper, RemoteOKScraper) for scraper in scrapers)


def test_load_sources_reads_yaml(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text(
        """
enabled_sources:
  france_travail: false
  remoteok: true
remoteok:
  max_jobs: 2
""",
        encoding="utf-8",
    )

    sources = load_sources(str(path))

    assert sources["enabled_sources"]["remoteok"] is True
    assert sources["remoteok"]["max_jobs"] == 2
