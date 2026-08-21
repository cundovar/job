from filters.keyword_filter import filter_by_keywords
from filters.location_filter import filter_by_location
from filters.contract_filter import filter_by_contract
from filters.sector_filter import filter_by_sector
from analyzers.scoring_engine import _score_location


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


def test_location_filter_accepts_all_idf_departments_and_accented_zones():
    criteria = {
        "location": {
            "accepted_zones": [
                "Île-de-France",
                "75", "77", "78", "91", "92", "93", "94", "95",
                "Hauts-de-Seine", "Yvelines", "Val-d'Oise", "Essonne",
                "Nanterre", "Versailles", "Cergy", "Massy",
            ],
            "remote_accepted": True,
            "hybrid_accepted": True,
        }
    }
    jobs = [
        {"title": "Dev", "location": "Nanterre (92)", "description": ""},
        {"title": "Dev", "location": "Versailles - Yvelines", "description": ""},
        {"title": "Dev", "location": "Cergy, Val-d'Oise", "description": ""},
        {"title": "Dev", "location": "Massy (91)", "description": ""},
        {"title": "Dev", "location": "Lyon", "description": ""},
    ]

    filtered = filter_by_location(jobs, criteria)

    assert [job["location"] for job in filtered] == [
        "Nanterre (92)",
        "Versailles - Yvelines",
        "Cergy, Val-d'Oise",
        "Massy (91)",
    ]


def test_location_scoring_accepts_west_south_north_idf():
    criteria = {"location": {"score_weights": {"paris": 10, "idf": 8, "remote": 10, "hybrid": 9}}}

    assert _score_location({"location": "Paris 15", "description": ""}, criteria) == 10
    assert _score_location({"location": "Nanterre (92)", "description": ""}, criteria) == 8
    assert _score_location({"location": "Versailles - Yvelines", "description": ""}, criteria) == 8
    assert _score_location({"location": "Massy (91)", "description": ""}, criteria) == 8
    assert _score_location({"location": "Cergy, Val-d'Oise", "description": ""}, criteria) == 8
    assert _score_location({"location": "Lyon", "description": ""}, criteria) == 0
