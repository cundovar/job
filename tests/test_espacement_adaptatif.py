"""Espacements selon le contenu (décision Cundo 23/10/2026)."""
from pypdf import PdfReader

from cv_generator.cv_pdf_design import MAX_GAP_STRETCH, _largest_fitting, page_fill
from cv_generator.cv_quality_checker import review_cv
from cv_generator.exporters import cv_to_pdf


def _cv(n_exp, n_bullets=2):
    return {"base_variant": "accueil", "cv": {
        "title": "Agent d'accueil", "profile": "Accroche fictive.", "contact": {}, "location": "Paris",
        "skills": [{"title": "Accueil", "items": ["Accueil physique"]}],
        "experiences": [
            {"title": f"Poste {i}", "organization": "Org fictive", "period": "2020 – 2021",
             "bullets": ["Puce fictive assez longue pour occuper une ligne entière du CV."] * n_bullets}
            for i in range(n_exp)
        ],
        "education": [{"year": 2012, "title": "CAP fictif"}],
    }}


def test_dichotomie_bornee():
    assert _largest_fitting(lambda v: True, 1.0, 1.8) == 1.8
    assert _largest_fitting(lambda v: False, 1.0, 1.8) == 1.0
    assert abs(_largest_fitting(lambda v: v <= 1.3, 1.0, 1.8) - 1.3) < 0.01


def test_remplissage_mesure():
    court, long_ = page_fill(_cv(2)), page_fill(_cv(9, 3))
    assert court < 0.6 < long_


def test_cv_court_et_cv_dense_tiennent_sur_une_page(tmp_path):
    for name, content in (("court", _cv(2)), ("dense", _cv(9, 3))):
        cv_to_pdf(content, tmp_path / f"{name}.pdf")
        assert len(PdfReader(str(tmp_path / f"{name}.pdf")).pages) == 1


def test_place_libre_signalee_sans_bloquer():
    review = review_cv({}, {"layout_constraints": {}, "forbidden_claims": []},
                       {"priority_keywords": [], "experience_plan": []}, _cv(2))
    hint = [p for p in review["problems"] if p.get("code") == "PAGE_SPACE_AVAILABLE"]
    assert hint and hint[0]["severity"] == "low" and hint[0]["path"] == "experiences"
    dense = review_cv({}, {"layout_constraints": {}, "forbidden_claims": []},
                      {"priority_keywords": [], "experience_plan": []}, _cv(9, 3))
    assert not [p for p in dense["problems"] if p.get("code") == "PAGE_SPACE_AVAILABLE"]


def test_etirement_plafonne():
    assert MAX_GAP_STRETCH <= 2.5
