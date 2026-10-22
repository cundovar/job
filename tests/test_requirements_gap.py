"""Écarts annonce / profil : diplôme et durée mesurés, rien de revendiqué à tort."""
from datetime import date

import pytest

from cv_generator import requirements_gap as rg

MASTER = {
    "person": {"education": [
        {"year": 2026, "title": "Titre professionnel concepteur (fictif)", "level": "niveau 6", "status": "VAE en cours"},
        {"year": 2019, "title": "Titre développeur web (fictif)", "level": "Bac+2"},
        {"year": 2012, "title": "CAP Petite Enfance"},
    ]},
    "experience_catalog": {
        "a": {"period": {"start": "2020-01", "end": "2021-12"}},
        "b": {"period": {"start": "2021-01", "end": "2022-12"}},       # chevauche a
        "c": {"period": {"start": "2010", "end": "2011"}, "retired": True},
        "d": {"period": {"start": "2024-01", "ongoing": True}},
    },
}
ANNONCE = """Missions : accompagner les publics.
Profil recherché
Niveau d'études : minimum Master 2 - Expérience demandée : au moins 2 ans.
Le but du poste est d'accompagner les familles."""


@pytest.mark.parametrize("texte, niveau", [
    ("Niveau d'études : minimum Master 2", 7),
    ("Diplôme Bac+5 exigé", 7),
    ("Titulaire d'une licence", 6),
    ("Formation : BTS ou DUT", 5),
    ("Niveau Bac requis", 4),
    ("Vous aimez le travail en équipe.", 0),
    ("Le but est d'aider", 0),
])
def test_niveau_exige(texte, niveau):
    assert rg.required_diploma(texte)[0] == niveau


def test_niveau_obtenu_hors_diplome_en_cours():
    level, title, in_progress = rg.candidate_diplomas(MASTER)
    assert level == 5 and "développeur" in title
    assert in_progress and "VAE" in in_progress[0]


def test_annees_couvertes_sans_doubler_les_chevauchements():
    years = rg.experience_years(MASTER, today=date(2026, 12, 31))
    assert years == pytest.approx(3 + 3)  # 2020-2022 (3 ans) + 2024-2026 (3 ans), c retirée


def test_ecart_diplome_detecte_et_compensation_de_l_agent_gardee():
    gaps = rg.detect_gaps(ANNONCE, MASTER, [
        {"type": "diplome", "exigence": "Master 2", "compensation": "Années de pratique en formation."},
        {"type": "experience", "exigence": "10 ans", "compensation": "x"},   # démenti par les données
        {"type": "competence", "exigence": "Permis B", "profil": "non mentionné"},
    ])
    types = [gap["type"] for gap in gaps]
    assert types == ["diplome", "competence"]
    diplome = gaps[0]
    assert diplome["source"] == "python" and "niveau 7" in diplome["exigence"]
    assert "niveau 5" in diplome["profil"] and "VAE" in diplome["profil"]
    assert diplome["compensation"] == "Années de pratique en formation."


def test_pas_d_ecart_quand_le_profil_couvre():
    assert rg.detect_gaps("Niveau Bac+2 requis. 2 ans d'expérience minimum.", MASTER) == []


def test_ecart_de_duree():
    gaps = rg.detect_gaps("Expérience : au moins 10 ans dans le secteur.", MASTER)
    assert [gap["type"] for gap in gaps] == ["experience"]


def test_durees_affirmees():
    assert rg.years_claims("Formateur avec 4 ans d'expérience et 2 ans d’expérience en médiation") == [4, 2]
