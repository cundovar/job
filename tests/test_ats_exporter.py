from cv_generator.ats_exporter import cv_to_ats_html, cv_to_ats_pdf
from cv_generator.ats_validator import extract_pdf_text, validate_ats_pdf


def _final_cv():
    return {
        "cv": {
            "title": "Développeur PHP / Symfony",
            "profile": "Développeur web orienté applications métier et API REST.",
            "contact": {"email": "facundo@example.test", "phone": "06 00 00 00 00"},
            "location": "Paris",
            "skills": [{"title": "Back-end", "items": ["PHP 8", "Symfony 7"]}],
            "experiences": [
                {
                    "id": "example",
                    "title": "Développeur back-end Symfony",
                    "organization": "Société Exemple",
                    "period": "2024-01 – 2025-12",
                    "bullets": ["Développement d’API métier en français."],
                }
            ],
            "projects": [],
            "education": [{"year": 2022, "title": "Développeur Web et Web Mobile", "level": "Bac+2"}],
            "languages": [{"name": "Français", "level": "courant"}],
        }
    }


def test_ats_html_is_single_column_and_has_no_decorative_media():
    html = cv_to_ats_html(_final_cv())

    assert "grid-template-columns" not in html
    assert "<img" not in html
    assert "<table" not in html
    assert "Facundo Varas" in html
    assert "Expériences professionnelles" in html


def test_ats_pdf_text_is_extractible_and_complete(tmp_path):
    path = tmp_path / "cv_ats.pdf"
    cv_to_ats_pdf(_final_cv(), path)

    text = extract_pdf_text(path)
    result = validate_ats_pdf(path, _final_cv())

    assert path.read_bytes().startswith(b"%PDF")
    assert "Facundo Varas" in text
    assert "Société Exemple" in text
    assert "Français" in text
    assert result["status"] == "pass"
    assert result["missing"] == []


def test_validator_reports_a_missing_essential_field(tmp_path):
    path = tmp_path / "cv_ats.pdf"
    cv_to_ats_pdf(_final_cv(), path)
    changed = _final_cv()
    changed["cv"]["experiences"][0]["organization"] = "Organisation absente du PDF"

    result = validate_ats_pdf(path, changed)

    assert result["status"] == "fail"
    assert "experience_0_organization" in result["missing"]
