"""Critères de recherche refondus le 18/11/2026 : axes A-D, sans périscolaire.

Chaque annonce type doit tomber du bon côté du filtre, avec la vraie
configuration (config/criteria.yaml).
"""
import pytest
import yaml

from analyzers.scoring_engine import calculate_score
from filters.keyword_filter import filter_by_keywords, title_excluded


@pytest.fixture(scope="module")
def criteria():
    with open("config/criteria.yaml", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _job(title, description="", company="Ville de Paris", contract="CDD"):
    return {"title": title, "description": description or title, "company": company,
            "location": "Paris", "contract_type": contract}


KEPT = [
    ("Animateur famille du centre socioculturel", "Ateliers parents-enfants, sorties familles, Relais petite enfance avec l'accueil de loisirs voisin."),
    ("Conseiller numérique France Services", "Accompagnement des usagers aux démarches en ligne."),
    ("Médiateur numérique (H/F)", "Ateliers d'inclusion numérique en EPN."),
    ("Agent d'accueil France Services", "Accueil physique et téléphonique, orientation des publics."),
    ("Webmaster", "Gestion du site WordPress de l'association."),
    ("Formateur web et IA", "Formation d'adultes en reconversion."),
    ("Animateur multimédia", "Ateliers numériques au centre social."),
]

EXCLUDED = [
    ("Animateur périscolaire (H/F)", "periscolaire"),
    ("Animateur enfance jeunesse", "animateur enfance"),
    ("Animatrice accueil de loisirs", "accueil de loisirs"),
    ("Directeur ALSH", "alsh"),
    ("Chargé d'insertion professionnelle", "charge d'insertion"),
    ("Conseiller emploi", "conseiller emploi"),
    ("Technicien support helpdesk", "helpdesk"),
    ("Responsable du pôle numérique", "responsable"),
]


@pytest.mark.parametrize(("title", "description"), KEPT)
def test_annonces_des_axes_gardees(criteria, title, description):
    job = _job(title, description)
    assert filter_by_keywords([job], criteria) == [job]
    assert calculate_score(dict(job), criteria) >= 55  # seuil « ignore »


@pytest.mark.parametrize(("title", "word"), EXCLUDED)
def test_annonces_hors_axes_ecartees_sur_le_titre(criteria, title, word):
    job = _job(title)
    assert title_excluded(job, criteria) == word
    assert filter_by_keywords([job], criteria) == []


def test_le_mot_dans_la_description_seule_n_ecarte_pas(criteria):
    job = _job("Référente famille", "Travail en lien avec l'accueil de loisirs et le périscolaire de la ville.")
    assert title_excluded(job, criteria) == ""
    assert filter_by_keywords([job], criteria) == [job]


def test_mots_entiers_seulement(criteria):
    assert title_excluded(_job("Médiateur numérique — irresponsable s'abstenir"), criteria) == ""
