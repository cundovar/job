from cv_generator import prepare_custom_cv


def test_prepare_custom_cv_generates_webmaster_files(tmp_path):
    job = {
        "title": "Webmaster WordPress / administrateur de site",
        "company": "Ville Test",
        "description": "Gestion CMS WordPress, maintenance, contenus, documentation et sensibilisation RGAA.",
        "url": "https://example.test/job",
        "score": 90,
    }

    result = prepare_custom_cv(job, application_dir=tmp_path, master_path="data/cv_master_profile.json")

    assert result["ok"] is True
    assert result["selected_base_variant"] == "webmaster"
    assert "Webmaster" in result["target_title"]
    assert (tmp_path / "cv" / "cv_final.json").exists()
    assert (tmp_path / "cv" / "cv_canva_copy.md").exists()
    canva = (tmp_path / "cv" / "cv_canva_copy.md").read_text(encoding="utf-8")
    assert "WordPress" in canva
    assert "Facundo Varas" in canva
