"""Éditeur du CV : expériences et projets du profil proposés à l'ajout (18/11/2026)."""
from cv_generator.user_edit import catalog_entries

MASTER = {
    "experience_catalog": {
        "chelles": {"organization": "Mairie de Chelles", "title": "Animateur périscolaire",
                    "period": {"start": "2013", "end": "2018"}, "highlights": ["Animation en centre de loisirs"]},
        "ancienne": {"organization": "X", "title": "Retirée", "retired": True, "highlights": ["a"]},
    },
    "person": {"education": [
        {"year": 2012, "title": "CAP Petite Enfance", "school": "Cours du soir"},
        {"year": 2026, "title": "Titre Professionnel CDA", "level": "niveau 6", "status": "VAE en cours"},
    ]},
    "project_catalog": {
        "mediateur": {"title": "Mediateur", "year": 2026, "description": "Site de formation.",
                      "technologies": ["Vue.js"], "links": ["https://mediateur.varascundo.com/"]},
    },
}


def test_catalogue_au_format_du_cv_sans_les_experiences_retirees():
    catalog = catalog_entries(MASTER)
    assert [e["id"] for e in catalog["experiences"]] == ["chelles"]
    exp = catalog["experiences"][0]
    assert exp["bullets"] == ["Animation en centre de loisirs"]
    assert "2013" in exp["period"] and "2018" in exp["period"]
    assert catalog["projects"][0]["year"] == "2026"
    assert catalog["projects"][0]["links"] == ["https://mediateur.varascundo.com/"]


def test_catalogue_vide_sans_profil():
    assert catalog_entries({}) == {"experiences": [], "projects": [], "education": []}


def test_diplomes_proposes_avec_leur_statut():
    education = catalog_entries(MASTER)["education"]
    assert education[0] == {"year": "2012", "title": "CAP Petite Enfance", "school": "Cours du soir"}
    assert education[1]["status"] == "VAE en cours"
