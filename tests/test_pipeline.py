from pathlib import Path

from pipeline import run_job_search


class FakeScraper:
    def scrape(self, keywords):
        return [
            {
                "title": "Webmaster WordPress",
                "company": "Ville Test",
                "location": "Paris",
                "contract_type": "CDI",
                "description": "Gestion CMS WordPress et documentation dans une association.",
                "url": "https://example.com/job",
                "source": "fake",
            }
        ]


def test_run_job_search_without_network_or_outputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MAX_AI_JOBS_PER_RUN", "0")
    monkeypatch.setattr("pipeline.build_scrapers", lambda sources: [FakeScraper()])

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "criteria.yaml").write_text(
        """
target_positions:
  - keywords: ["webmaster", "wordpress"]
    score_weight: 60
red_flags:
  keywords: []
  hard_exclude_keywords: []
  hard_exclude_keywords_tech: []
  exclude_if_contains: []
  keep_if_contains: []
location:
  accepted_zones: ["Paris"]
  remote_accepted: true
  hybrid_accepted: true
  score_weights:
    paris: 10
contracts:
  accepted:
    - type: "CDI"
      score_weight: 15
  rejected: []
sectors:
  ess:
    keywords: ["association"]
    score_weight: 10
scoring:
  thresholds:
    basic_ai_analysis: 90
  bonus_points:
    salary_mentioned: 0
email:
  content:
    max_jobs_in_email: 5
user_profile:
  name: "Facundo Varas"
""",
        encoding="utf-8",
    )
    (config_dir / "sources.yaml").write_text("enabled_sources: {}\n", encoding="utf-8")

    result = run_job_search(send_outputs=False)

    assert result["all_jobs_count"] == 1
    assert result["stats"]["total"] == 1
    assert result["jobs"][0]["score"] == 95
    assert result["jobs"][0]["ai_analysis"]["recommandation"] == "PEUT-ÊTRE"
    assert Path("data/jobs_cache.json").exists()
