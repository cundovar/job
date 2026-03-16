from filters.keyword_filter import filter_by_keywords
from filters.location_filter import filter_by_location
from filters.contract_filter import filter_by_contract
from filters.sector_filter import filter_by_sector


def test_filters_basic():
    criteria = {
        "target_positions": [{"keywords": ["formateur web"]}],
        "red_flags": {"keywords": ["stage"], "sectors_to_exclude": []},
        "location": {"accepted_zones": ["Paris"], "remote_accepted": True, "hybrid_accepted": True},
        "contracts": {"accepted": [{"type": "CDI"}], "rejected": ["Stage"]},
        "sectors": {"ess": {"keywords": ["association"], "score_weight": 30}},
    }

    jobs = [
        {
            "title": "Formateur web",
            "description": "Association éducative",
            "location": "Paris",
            "contract_type": "CDI",
            "company": "Asso",
        },
        {
            "title": "Formateur web",
            "description": "Stage en association",
            "location": "Paris",
            "contract_type": "Stage",
            "company": "Asso",
        },
    ]

    jobs = filter_by_keywords(jobs, criteria)
    assert len(jobs) == 1

    jobs = filter_by_location(jobs, criteria)
    assert len(jobs) == 1

    jobs = filter_by_contract(jobs, criteria)
    assert len(jobs) == 1

    jobs = filter_by_sector(jobs, criteria)
    assert len(jobs) == 1


def test_keyword_filter_excludes_unrelated_project_manager_jobs():
    criteria = {
        "target_positions": [
            {"keywords": ["webmaster", "formateur developpement web", "formateur ia"]},
        ],
        "red_flags": {
            "keywords": [],
            "hard_exclude_keywords": [],
            "hard_exclude_keywords_tech": [],
            "exclude_if_contains": [],
            "keep_if_contains": [],
        },
    }

    jobs = [
        {
            "title": "Chef de projet digital",
            "description": "Pilotage de projets web et coordination prestataires",
        },
        {
            "title": "Webmaster WordPress",
            "description": "Gestion de site institutionnel et accessibilite",
        },
        {
            "title": "Formateur developpement web et IA",
            "description": "Animation de formations HTML, JavaScript et IA generative",
        },
    ]

    filtered = filter_by_keywords(jobs, criteria)

    assert [job["title"] for job in filtered] == [
        "Webmaster WordPress",
        "Formateur developpement web et IA",
    ]
