"""Sources de recherche revues le 18/11/2026 : nouveaux sites, âge des offres,
limites de collecte, offres non analysées par l'IA."""
from datetime import date

import pipeline
from filters.date_filter import filter_by_age, parse_published
from front_export import was_ai_analyzed
from scrapers.choisir_service_public_scraper import parse_detail, parse_listing, parse_online_since
from scrapers.hellowork_scraper import age_in_days
from scrapers.hellowork_scraper import parse_listing as hellowork_listing

CSP_CARD = """
<ul><li><div class="fr-card fr-card--horizontal"><div class="fr-card__content">
<h3 class="fr-card__title"><a href="https://choisirleservicepublic.gouv.fr/offre-emploi/mediateur-numerique---mairie-de-argenteuil-reference-O095260713000904/">
Médiateur numérique - Mairie de ARGENTEUIL</a></h3>
<div class="fr-card__start"><ul class="fr-tags-group"><li><p class="fr-tag">Lecture publique</p></li></ul></div>
<ul class="fr-card__desc">
<li><span class="sr-only">Localisation : </span> Val d'Oise <strong>(95)</strong></li>
<li><span class="sr-only">Fonction publique : </span> Fonction publique Territoriale</li>
<li><span class="sr-only">Employeur : </span> Communes</li>
<li class="fr-icon-calendar-line"> En ligne depuis le 10 novembre 2026</li>
</ul></div></div></li></ul>
"""

CSP_DETAIL = """<script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting",
"title":"Médiateur numérique","hiringOrganization":"Mairie d'Argenteuil",
"Description":"<p>Animer des ateliers <b>numériques</b>.</p>","experienceRequirements":"Débutant accepté",
"datePosted":"09/10/2026"}</script>"""

HELLOWORK_CARD = """
<ul><li>
<a data-cy="offerTitle" href="/fr-fr/emplois/79556477.html" title="Vacataire Animateur et Médiation Numérique H/F - Saint Quentin en Yvelines Agglomération">
<p>Vacataire Animateur et Médiation Numérique H/F</p><p>Saint Quentin en Yvelines Agglomération</p></a>
<div>Élancourt - 78</div><div>CDD</div><div>Temps partiel</div><div>il y a 6 jours</div>
</li></ul>
"""


def test_choisir_service_public_liste_et_fiche():
    [card] = parse_listing(CSP_CARD)
    assert card["title"] == "Médiateur numérique - Mairie de ARGENTEUIL"
    assert card["location"] == "Val d'Oise (95)"
    assert card["company"] == "Communes"
    assert card["published_at"] == "2026-11-10"
    detail = parse_detail(CSP_DETAIL)
    assert detail["company"] == "Mairie d'Argenteuil"
    assert "Animer des ateliers numériques." in detail["description"]
    assert "Débutant accepté" in detail["description"]
    assert parse_online_since("En ligne depuis le 1er mars 2026") == "2026-03-01"


def test_hellowork_carte():
    [card] = hellowork_listing(HELLOWORK_CARD)
    assert card["title"] == "Vacataire Animateur et Médiation Numérique H/F"
    assert card["company"] == "Saint Quentin en Yvelines Agglomération"
    assert card["location"] == "Élancourt - 78"
    assert card["contract_type"] == "CDD"
    assert card["age_days"] == 6
    assert card["url"] == "https://www.hellowork.com/fr-fr/emplois/79556477.html"
    assert age_in_days("il y a 2 mois") == 60
    assert age_in_days("Hier") == 1


def test_filtre_par_age_garde_les_dates_inconnues():
    criteria = {"scraping": {"max_job_age_days": 14}}
    jobs = [
        {"title": "récente", "published_at": "2026-11-10"},
        {"title": "ancienne", "published_at": "2026-09-01T08:00:00Z"},
        {"title": "rss", "published_at": "Tue, 17 Nov 2026 08:00:00 +0100"},
        {"title": "fr", "published_at": "01/10/2026"},
        {"title": "sans date", "published_at": ""},
        {"title": "illisible", "published_at": "bientôt"},
    ]
    kept = [job["title"] for job in filter_by_age(jobs, criteria, today=date(2026, 11, 18))]
    assert kept == ["récente", "rss", "sans date", "illisible"]
    assert parse_published("18/11/2026") == date(2026, 11, 18)


def test_limites_de_sources_yaml(monkeypatch):
    monkeypatch.setenv("MAX_JOBS_PER_SITE", "120")
    monkeypatch.setenv("MAX_KEYWORDS_PER_SOURCE", "10")
    pipeline.apply_source_limits({"limits": {"max_keywords_per_source": 24, "max_jobs_per_site": 240}})
    import os
    assert os.environ["MAX_KEYWORDS_PER_SOURCE"] == "24"
    assert os.environ["MAX_JOBS_PER_SITE"] == "240"


def test_sources_actives_et_coupees():
    sources = pipeline.load_sources("config/sources.yaml")
    enabled = sources["enabled_sources"]
    assert enabled["choisir_service_public"] and enabled["hellowork"]
    assert not enabled["apec"] and not enabled["indeed"] and not enabled["wttj"]
    names = {type(s).__name__ for s in pipeline.build_scrapers(sources)}
    assert {"ChoisirServicePublicScraper", "HelloworkScraper", "FranceTravailScraper"} <= names
    assert "APECScraper" not in names


def test_offre_hors_plafond_ia_reste_candidate():
    assert was_ai_analyzed({"ai_analysis": {"recommandation": "POSTULER", "raison_breve": "Bon profil."}})
    assert not was_ai_analyzed({"ai_analysis": {"raison_breve": "Analyse IA non disponible sur ce run."}})
    assert not was_ai_analyzed({"ai_analysis": {"ia_non_analysee": True, "raison_breve": "x"}})
    assert not was_ai_analyzed({})


def test_recap_par_mail_coupe_par_defaut():
    """Décision du 18/11/2026 : plus de récap par mail à chaque recherche."""
    criteria = pipeline.load_criteria("config/criteria.yaml")
    assert criteria["email"]["send_daily"] is False
