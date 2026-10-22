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


def test_coordonnees_revues_par_le_candidat_et_champs_inconnus_ignores(dossier):
    # Le candidat a la main sur ses coordonnées (demande Cundo 22/10/2026).
    edited = _edited(contact={"email": "autre@exemple.test", "phone": "", "portfolio": "https://site.exemple.test/"},
                     location="Montreuil", script="<x>")
    cv = user_edit.save_user_edit(dossier, edited, {})["cv"]
    assert cv["contact"] == {"email": "autre@exemple.test", "portfolio": "https://site.exemple.test/"}
    assert cv["location"] == "Montreuil"
    assert "script" not in cv


def test_sans_saisie_les_coordonnees_de_la_generation_restent(dossier):
    edited = _edited()
    edited.pop("contact"); edited.pop("location")
    cv = user_edit.save_user_edit(dossier, edited, {})["cv"]
    assert cv["contact"] == {"email": "contact@exemple.test"} and cv["location"] == "Paris"


@pytest.mark.parametrize("contact, message", [
    ({"email": "pas-un-email"}, "email"),
    ({"phone": "appelle-moi"}, "téléphone"),
    ({"portfolio": "javascript:alert(1)"}, "portfolio"),
    ({"github": "https://docdevdoc.varascundo.com"}, "github"),
])
def test_coordonnee_invalide_refusee(dossier, contact, message):
    with pytest.raises(user_edit.UserEditError, match=message):
        user_edit.save_user_edit(dossier, _edited(contact=contact), {})


def test_show_rend_les_realisations_affichees(dossier, capsys):
    assert user_edit.main([str(dossier), "--show"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] and out["edited"] is False and out["cv"]["title"] == "Développeur"
    assert isinstance(out["online_work_effective"], list)


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
