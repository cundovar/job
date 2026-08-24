import json
from pathlib import Path

from applications import build_application_package


def test_build_application_package_creates_expected_files(tmp_path):
    job = {
        "title": "Webmaster institutionnel WordPress",
        "company": "Ville Test",
        "location": "Paris",
        "contract_type": "CDI",
        "source": "test",
        "url": "https://example.com/job",
        "score": 86,
        "description": "Gestion CMS WordPress, accessibilite RGAA et site institutionnel.",
        "ai_analysis": {"recommandation": "POSTULER"},
    }

    package = build_application_package(job, output_dir=str(tmp_path))

    assert Path(package.directory).exists()
    assert Path(package.job_path).exists()
    assert Path(package.resume_path).exists()
    assert Path(package.cv_recommendation_path).exists()
    assert Path(package.motivation_letter_path).exists()
    assert Path(package.application_email_path).exists()
    assert Path(package.metadata_path).exists()
    assert package.recommended_cv.cv_id == "webmaster"

    saved_job = json.loads(Path(package.job_path).read_text(encoding="utf-8"))
    assert saved_job == job

    metadata = json.loads(Path(package.metadata_path).read_text(encoding="utf-8"))
    assert metadata["job_title"] == "Webmaster institutionnel WordPress"
    assert metadata["company"] == "Ville Test"
    assert metadata["status"] == "ready_to_apply"
    assert metadata["recommended_cv"]["cv_id"] == "webmaster"


def test_build_application_package_uses_slugged_directory(tmp_path):
    job = {
        "title": "Administrateur applicatif / support fonctionnel",
        "company": "Association Exemple",
        "description": "Support applicatif, SQL, ERP et documentation.",
    }

    package = build_application_package(job, output_dir=str(tmp_path))

    directory_name = Path(package.directory).name
    assert "association-exemple" in directory_name
    assert "administrateur-applicatif-support-fonctionnel" in directory_name
    assert package.recommended_cv.cv_id in ("dev_fullstack", "webmaster")
