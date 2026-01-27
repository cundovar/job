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
