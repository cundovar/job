from analyzers.scoring_engine import calculate_score


def test_scoring_higher_for_formateur_ess():
    criteria = {
        "target_positions": [
            {"keywords": ["formateur web"], "score_weight": 40},
            {"keywords": ["chef de projet"], "score_weight": 35},
        ],
        "sectors": {"ess": {"keywords": ["association"], "score_weight": 30}},
        "contracts": {"accepted": [{"type": "CDI", "score_weight": 15}]},
        "location": {"score_weights": {"paris": 10}},
        "scoring": {"bonus_points": {"salary_mentioned": 5}},
    }

    job = {
        "title": "Formateur web",
        "description": "Association éducative",
        "company": "Asso",
        "contract_type": "CDI",
        "location": "Paris",
        "salary": "40k",
    }

    score = calculate_score(job, criteria)
    assert score >= 80
