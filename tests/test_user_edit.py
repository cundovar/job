"""Ta version du CV : nettoyée, rendue sans IA, jamais jugée par la véracité."""
import json

import pytest

from cv_generator import user_edit

GENERATED = {
    "agent": "cv_creator_ai",
    "base_variant": "fullstack",
    "generated_for": {"job_title": "Poste fictif"},
    "cv": {
        "title": "Développeur",
        "profile": "Accroche.",
        "contact": {"email": "contact@exemple.test"},
        "location": "Paris",
        "section_order": ["profile", "experiences", "skills", "projects", "education"],
        "experiences": [{"id": "agence", "organization": "Agence", "title": "Dev", "period": "2024", "bullets": ["Puce."]}],
        "skills": [{"title": "Web", "items": ["PHP"]}],
        "projects": [],
        "education": [{"year": "2020", "title": "Diplôme fictif"}],
        "languages": ["Français"],
    },
}


@pytest.fixture
def dossier(tmp_path):
    (tmp_path / "cv").mkdir()
    (tmp_path / "cv" / "cv_content.json").write_text(json.dumps(GENERATED), encoding="utf-8")
    return tmp_path


def _edited(**changes):
    cv = json.loads(json.dumps(GENERATED["cv"]))
    cv.update(changes)
    return cv


def test_une_experience_absente_du_profil_peut_etre_ajoutee(dossier):
    edited = _edited(experiences=GENERATED["cv"]["experiences"] + [
        {"organization": "Magasin fictif", "title": "Vendeur", "period": "2026", "bullets": ["Conseil client."]}
    ])
    content = user_edit.save_user_edit(dossier, edited, {})
    assert [e["organization"] for e in content["cv"]["experiences"]] == ["Agence", "Magasin fictif"]
    assert (dossier / "cv" / "cv_edit.pdf").read_bytes().startswith(b"%PDF")
    assert (dossier / "cv" / "cv_edit_ats.pdf").read_bytes().startswith(b"%PDF")
    assert content["agent"] == "edition_candidat"


def test_coordonnees_gardees_et_champs_inconnus_ignores(dossier):
    edited = _edited(contact={"email": "pirate@exemple.test"}, script="<x>")
    content = user_edit.save_user_edit(dossier, edited, {})
    assert content["cv"]["contact"] == {"email": "contact@exemple.test"}
    assert "script" not in content["cv"]


def test_liens_nettoyes_et_lien_retire_exclu(dossier):
    edited = _edited(
        experiences=[{"organization": "A", "title": "B", "bullets": ["c"],
                      "links": ["javascript:alert(1)", "https://docdevdoc.varascundo.com", "https://exemple.test"]}],
        online_work=[{"label": "doc", "url": "https://docdevdoc.varascundo.com"}, {"label": "ok", "url": "https://exemple.test/x"}],
    )
    cv = user_edit.save_user_edit(dossier, edited, {})["cv"]
    assert cv["experiences"][0]["links"] == ["https://exemple.test"]
    assert cv["online_work"] == [{"label": "ok", "url": "https://exemple.test/x"}]


def test_depassements_signales_sans_bloquer(dossier):
    master = {"layout_constraints": {"max_profile_chars": 10, "max_bullet_chars": 3}}
    content = user_edit.save_user_edit(dossier, _edited(profile="Une accroche bien trop longue."), master)
    assert any("Accroche" in w for w in content["warnings"])
    assert any("Puce" in w for w in content["warnings"])


@pytest.mark.parametrize("cv, message", [
    ({"title": "", "experiences": [{"title": "x"}]}, "titre"),
    ({"title": "T", "experiences": []}, "expérience"),
])
def test_version_inutilisable_refusee_sans_ecraser(dossier, cv, message):
    with pytest.raises(user_edit.UserEditError, match=message):
        user_edit.save_user_edit(dossier, cv, {})
    assert not (dossier / "cv" / "cv_edit.json").exists()


def test_reset_et_cli(dossier, capsys):
    path = dossier / "in.json"
    path.write_text(json.dumps({"cv": _edited(title="Mon titre")}), encoding="utf-8")
    assert user_edit.main([str(dossier), "--input", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert user_edit.current_content(dossier / "cv")["cv"]["title"] == "Mon titre"
    assert user_edit.main([str(dossier), "--reset"]) == 0
    assert sorted(json.loads(capsys.readouterr().out)["removed"]) == sorted(user_edit.EDIT_FILES)
    assert user_edit.current_content(dossier / "cv")["cv"]["title"] == "Développeur"
