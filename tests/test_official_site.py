"""La recherche du site officiel d'un candidat du registre.

Le besoin qui a produit ces tests : « la recherche par annuaire ne donne que du
bruit ». Elle en donnait parce qu'un candidat du registre arrivait sans site,
donc sans auto-description, donc en `incertain 0/100` — KONEXIO, organisme de
formation, s'affichait « Agence 0/100 ».

Ce que ces tests verrouillent tient en une phrase : **sans preuve, on ignore**.
Aucun domaine n'est déduit d'un nom, aucun annuaire n'est pris pour un site, et
un refus est toujours motivé plutôt que silencieux.

La suite tourne hors ligne : moteur et crawl sont injectés.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, relative: str):
    """`tools/` n'est pas un package : on charge par chemin, comme les autres suites."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


os_site = _load('official_site', 'tools/official_site.py')


KONEXIO = {
    'name': 'KONEXIO',
    'siren': '812345678',
    'siret': '81234567800021',
    'legal_address': '9 RUE DE LA PIERRE LEVEE 75011 PARIS',
    'commune_label': 'Paris',
}


# ── Ce qui n'est jamais un site officiel ─────────────────────────────────────


@pytest.mark.parametrize('url, expected', [
    ('https://www.societe.com/societe/konexio-812345678.html', os_site.EXCLUSION_DIRECTORY),
    ('https://www.pappers.fr/entreprise/konexio-812345678', os_site.EXCLUSION_DIRECTORY),
    ('https://manageo.fr/konexio', os_site.EXCLUSION_DIRECTORY),
    ('https://annuaire-entreprises.data.gouv.fr/entreprise/konexio', os_site.EXCLUSION_DIRECTORY),
    ('https://www.linkedin.com/company/konexio', os_site.EXCLUSION_PROFILE),
    ('https://www.pagesjaunes.fr/pros/konexio', os_site.EXCLUSION_DIRECTORY),
    ('https://fonts.gstatic.com/', os_site.EXCLUSION_INFRA),
    ('https://d3e54v103j8qbb.cloudfront.net/', os_site.EXCLUSION_INFRA),
    ('https://cdn.example.com/', os_site.EXCLUSION_INFRA),
    ('https://konexio.eu/', None),
])
def test_an_excluded_host_is_named_not_merely_dropped(url, expected):
    """Un annuaire cite le SIREN et l'adresse : c'est *lui* qui passerait le
    mieux la vérification. Il faut donc l'écarter avant de vérifier, et dire
    pourquoi — un rejet muet se relirait comme « rien trouvé »."""
    assert os_site.exclusion_reason(url) == expected


# ── La preuve ────────────────────────────────────────────────────────────────


def test_a_displayed_siret_is_the_strongest_proof():
    pages = [
        ('https://konexio.eu/', 'Konexio, association loi 1901'),
        ('https://konexio.eu/mentions-legales',
         'Mentions légales — SIRET 812 345 678 00021 — 9 rue de la Pierre Levée'),
    ]
    match, evidence = os_site.verify_site(KONEXIO, pages)
    assert match == os_site.SITE_MATCH_SIRET
    assert '81234567800021' in evidence
    assert 'mentions-legales' in evidence


def test_separators_between_digits_are_decorative():
    """« 812 345 678 » et « 812.345.678 » sont le même SIREN. Exiger la forme
    compacte reviendrait à rater la quasi-totalité des mentions légales."""
    pages = [('https://konexio.eu/mentions-legales', 'RCS Paris 812.345.678')]
    match, _ = os_site.verify_site({'name': 'KONEXIO', 'siren': '812345678'}, pages)
    assert match == os_site.SITE_MATCH_SIREN


def test_a_siren_is_not_found_inside_a_longer_number():
    """Neuf chiffres pris au milieu d'un numéro plus long ne sont pas un SIREN.
    Sans bornes, un identifiant de commande suffirait à « prouver » un site."""
    pages = [('https://ailleurs.fr/', 'Commande n° 9981234567890123')]
    match, _ = os_site.verify_site({'name': 'X', 'siren': '812345678'}, pages)
    assert match == os_site.SITE_MATCH_NONE


def test_an_address_needs_both_postal_code_and_street():
    """Un code postal seul désigne un quartier, un nom de rue seul se répète
    dans toute la France. Les deux, dans la même page, valent rapprochement —
    exactement le seuil que `city_match` applique à la commune."""
    both = [('https://konexio.eu/contact', 'Nous trouver : 9 rue de la Pierre Levée, 75011 Paris')]
    assert os_site.verify_site(KONEXIO, both)[0] == os_site.SITE_MATCH_ADDRESS

    postal_only = [('https://ailleurs.fr/contact', 'Nos bureaux sont à Paris 75011.')]
    assert os_site.verify_site(KONEXIO, postal_only)[0] == os_site.SITE_MATCH_NONE

    street_only = [('https://ailleurs.fr/contact', 'rue de la Pierre Levée, quelque part')]
    assert os_site.verify_site(KONEXIO, street_only)[0] == os_site.SITE_MATCH_NONE


def test_a_name_in_the_body_is_a_mention_not_an_attribution():
    """Même distinction que `city_match` : le nom doit *porter* la page — le
    domaine ou le titre —, pas y être cité. Une page de partenaire, de client ou
    d'actualité cite un nom sans lui appartenir."""
    cited = [('https://un-partenaire.fr/', 'Nous avons accompagné Konexio sur son programme.')]
    match, evidence = os_site.verify_site(KONEXIO, cited, title='Un Partenaire — accueil')
    assert match == os_site.SITE_MATCH_NONE
    assert 'cité dans la page' in evidence  # le refus est motivé, pas muet

    owned = [('https://konexio.eu/', 'Konexio')]
    assert os_site.verify_site(KONEXIO, owned)[0] == os_site.SITE_MATCH_NAME


def test_the_legal_form_does_not_carry_the_match():
    """« KONEXIO SAS » et « Konexio » sont la même structure ; « SAS » tout seul
    ne rapproche rien."""
    assert os_site.normalize_label('KONEXIO SAS') == 'konexio'
    assert os_site.normalize_label('Société Konexio') == 'konexio'


def test_strength_order_is_total_and_none_is_the_floor():
    ordered = [os_site.SITE_MATCH_NONE, os_site.SITE_MATCH_CONVERGENT, os_site.SITE_MATCH_NAME,
               os_site.SITE_MATCH_ADDRESS, os_site.SITE_MATCH_SIREN, os_site.SITE_MATCH_SIRET]
    strengths = [os_site.SITE_MATCH_STRENGTH[m] for m in ordered]
    assert strengths == sorted(strengths)
    assert os_site.SITE_MATCH_STRENGTH[os_site.SITE_MATCH_NONE] == 0


# ── La recherche de bout en bout ─────────────────────────────────────────────


def _fake_world(pages_by_host: dict[str, list[tuple[str, str]]],
                results: dict[str, list[str]],
                titles: dict[str, str] | None = None):
    calls: list[str] = []

    def search(query: str) -> list[str]:
        calls.append(query)
        return results.get(query, results.get('*', []))

    def crawl(url: str):
        host = os_site.host_of(url)
        return pages_by_host.get(host, []), (titles or {}).get(host, '')

    return search, crawl, calls


def test_a_registry_candidate_whose_site_shows_its_siren_is_retained():
    search, crawl, _ = _fake_world(
        pages_by_host={'konexio.eu': [
            ('https://konexio.eu/mentions-legales', 'SIREN 812 345 678'),
        ]},
        results={'*': ['https://www.societe.com/societe/konexio.html', 'https://konexio.eu/']},
    )
    outcome = os_site.find_official_site(KONEXIO, search, crawl)
    assert outcome['website'] == 'https://konexio.eu/'
    assert outcome['site_match'] == os_site.SITE_MATCH_SIREN
    assert '812345678' in outcome['site_match_evidence']
    # L'annuaire écarté reste listé avec son motif.
    excluded = [c for c in outcome['site_candidates'] if 'societe.com' in (c['website'] or '')]
    assert excluded and excluded[0]['evidence'] == os_site.EXCLUSION_DIRECTORY


def test_without_proof_nothing_is_retained_and_the_refusal_is_readable():
    """Le cas qui produisait le bruit : un homonyme commercial plausible. Sans
    SIREN, sans adresse et sans titre concordants, on n'attribue rien."""
    search, crawl, _ = _fake_world(
        pages_by_host={'konexio-formation.fr': [
            ('https://konexio-formation.fr/', 'Bienvenue sur notre site de formation.'),
        ]},
        results={'*': ['https://konexio-formation.fr/']},
        titles={'konexio-formation.fr': 'Formations en ligne'},
    )
    outcome = os_site.find_official_site(KONEXIO, search, crawl)
    assert outcome['website'] is None
    assert outcome['site_match'] == os_site.SITE_MATCH_NONE
    assert outcome['site_candidates']  # nommé, pas effacé


def test_no_domain_is_ever_guessed_from_the_name():
    """Le réflexe dangereux : `KONEXIO` → `konexio.fr`. Quand le moteur ne rend
    rien, la fonction ne rend rien — elle ne fabrique pas l'adresse qui tombe
    bien."""
    search, crawl, calls = _fake_world(pages_by_host={}, results={'*': []})
    outcome = os_site.find_official_site(KONEXIO, search, crawl)
    assert outcome['website'] is None
    assert calls, 'la recherche doit bien avoir été tentée'
    assert not any('konexio.fr' in str(c) for c in outcome['site_candidates'])


def test_a_dead_search_engine_does_not_invent_a_site():
    def search(query):
        raise RuntimeError('moteur indisponible')

    def crawl(url):
        raise AssertionError('aucun crawl ne doit être tenté sans résultat de recherche')

    outcome = os_site.find_official_site(KONEXIO, search, crawl)
    assert outcome['website'] is None
    assert any('indisponible' in c['evidence'] for c in outcome['site_candidates'])


def test_a_siret_stops_the_search_before_paying_for_more_pages():
    crawled: list[str] = []

    def search(query):
        return ['https://konexio.eu/', 'https://autre.fr/']

    def crawl(url):
        crawled.append(url)
        if 'konexio.eu' in url:
            return [('https://konexio.eu/mentions-legales', 'SIRET 81234567800021')], ''
        return [('https://autre.fr/', 'rien')], ''

    outcome = os_site.find_official_site(KONEXIO, search, crawl)
    assert outcome['site_match'] == os_site.SITE_MATCH_SIRET
    assert crawled == ['https://konexio.eu/'], 'rien ne bat un SIRET : on s’arrête'


def test_converging_sources_means_several_engines_not_several_queries():
    """Deux moteurs indépendants qui désignent le même domaine valent indice
    d'usage. C'est admis, et c'est classé dernier : la structure n'a rien
    déclaré elle-même."""
    def search(query):
        return [('https://konexio.eu/', 'ddg'), ('https://konexio.eu/', 'bing')]

    def crawl(url):
        return [('https://konexio.eu/', 'formation numérique')], 'Formation numérique'

    outcome = os_site.find_official_site(
        {'name': 'Structure Sans Nom Commun', 'commune_label': 'Paris'}, search, crawl)
    assert outcome['site_match'] == os_site.SITE_MATCH_CONVERGENT
    assert os_site.SITE_MATCH_STRENGTH[outcome['site_match']] == 1


def test_the_same_engine_answering_three_times_is_not_a_convergence():
    """Les trois requêtes posées contiennent toutes le nom : le même moteur rend
    forcément le même domaine. C'est un avis répété, pas une confirmation — et
    c'était le trou par lequel un homonyme passait."""
    def search(query):
        return [('https://konexio-formation.fr/', 'ddg')]

    def crawl(url):
        return [('https://konexio-formation.fr/', 'formations')], 'Formations en ligne'

    outcome = os_site.find_official_site(
        {'name': 'Structure Sans Nom Commun', 'commune_label': 'Paris'}, search, crawl)
    assert outcome['website'] is None
    assert outcome['site_match'] == os_site.SITE_MATCH_NONE


def test_an_undeclared_source_never_converges_on_its_own():
    """Sans provenance déclarée, on compte une seule source. Un défaut qui
    prouve tout seul serait un défaut dangereux."""
    search, crawl, _ = _fake_world(
        pages_by_host={'konexio.eu': [('https://konexio.eu/', 'formation')]},
        results={'*': ['https://konexio.eu/']},
        titles={'konexio.eu': 'Formation'},
    )
    outcome = os_site.find_official_site(
        {'name': 'Structure Sans Nom Commun', 'commune_label': 'Paris'}, search, crawl)
    assert outcome['website'] is None


def test_a_candidate_without_a_name_is_refused_not_searched():
    def search(query):
        raise AssertionError('rien à chercher sans raison sociale')

    outcome = os_site.find_official_site({'siren': '812345678'}, search, lambda u: ([], ''))
    assert outcome['website'] is None
    assert 'sans raison sociale' in outcome['site_candidates'][0]['evidence']


# ── Le câblage dans le prospecteur ───────────────────────────────────────────

v2 = _load('agency_prospecting_v2', 'tools/agency_prospecting_v2.py')


def test_a_registry_row_starts_without_a_site_and_says_so():
    """`aucun` veut dire « rien d'établi », pas « rien à chercher ». Le champ
    existe dès la création de la fiche pour que son absence ne se relise pas
    comme « on n'a pas regardé »."""
    row = v2.registry_record(
        {'name': 'KONEXIO', 'siren': '812345678', 'legal_address': '9 RUE X 75011 PARIS'},
        'ville-paris-75')
    assert row['website'] is None
    assert row['site_match'] == os_site.SITE_MATCH_NONE
    assert row['site_candidates'] == []
    assert row['category'] == 'incertain'  # le registre ne rend toujours aucun verdict


def test_resolve_registry_sites_counts_refusals_by_motive():
    """« 22 ignorés faute de site » et « 22 ignorés parce que le moteur n'a rendu
    que des annuaires » ne se corrigent pas de la même façon. Un compteur global
    les confondrait."""
    rows = [
        v2.registry_record({'name': 'Konexio', 'siren': '812345678'}, 'z'),
        v2.registry_record({'name': 'Introuvable'}, 'z'),
        v2.registry_record({'name': 'QueDesAnnuaires'}, 'z'),
    ]

    def search(query):
        if 'Konexio' in query:
            return ['https://konexio.eu/']
        if 'QueDesAnnuaires' in query:
            return ['https://www.societe.com/societe/quedesannuaires.html']
        return []

    def crawl(url):
        return [('https://konexio.eu/mentions-legales', 'SIREN 812 345 678')], ''

    stats = v2.resolve_registry_sites(rows, search=search, crawl=crawl)
    assert stats['trouves'] == 1
    assert rows[0]['website'] == 'https://konexio.eu/'
    assert rows[0]['site_match'] == os_site.SITE_MATCH_SIREN
    assert stats['motifs'][v2.MOTIF_NO_CANDIDATE] == 1
    assert stats['motifs'][v2.MOTIF_ONLY_EXCLUDED] == 1
    # Le site retenu laisse une trace lisible dans les raisons de la fiche.
    assert any('site officiel retenu' in r for r in rows[0]['reasons'])


def test_the_lookup_cap_is_announced_not_silent():
    """Le plafond protège la durée d'une passe. Un candidat non cherché doit le
    dire : sinon « sans preuve » et « pas regardé » deviennent le même chiffre."""
    rows = [v2.registry_record({'name': f'Structure {i}'}, 'z') for i in range(4)]
    stats = v2.resolve_registry_sites(rows, cap=2, search=lambda q: [], crawl=lambda u: ([], ''))
    assert stats['examines'] == 2
    assert stats['motifs'][v2.MOTIF_CAPPED] == 2
    assert 'plafond' in rows[3]['site_match_evidence']


def test_a_row_that_already_has_a_site_is_not_searched_again():
    rows = [v2.registry_record({'name': 'Déjà là'}, 'z')]
    rows[0]['website'] = 'https://deja-la.fr/'

    def search(query):
        raise AssertionError('un site connu ne se recherche pas')

    stats = v2.resolve_registry_sites(rows, search=search, crawl=lambda u: ([], ''))
    assert stats['examines'] == 0


def test_infrastructure_domains_never_become_candidates():
    """`fonts.gstatic.com` et un CDN CloudFront entraient dans les graines parce
    qu'ils sont liés depuis les pages crawlées, puis ressortaient en « page
    d'accueil illisible ». Ce sont des dépendances techniques."""
    assert v2.is_bad_host('fonts.gstatic.com')
    assert v2.is_bad_host('d3e54v103j8qbb.cloudfront.net')
    assert not v2.is_bad_host('konexio.eu')
    # Les annuaires utilisés comme sources de liens restent fréquentables.
    assert not v2.is_bad_host('sortlist.fr')


def test_the_proof_survives_deduplication():
    """Un `site_match` perdu à la fusion rendrait l'acceptation incontestable :
    la fiche afficherait un site sans dire ce qui l'y rattache."""
    registry = v2.registry_record({'name': 'Konexio', 'siren': '812345678'}, 'z')
    registry.update({'website': 'https://konexio.eu/',
                     'site_match': os_site.SITE_MATCH_SIREN,
                     'site_match_evidence': 'SIREN 812345678 affiché sur https://konexio.eu/mentions-legales'})
    merged = v2.compose_record({'members': [registry], 'match': 'siren', 'conflicts': []})
    assert merged['site_match'] == os_site.SITE_MATCH_SIREN
    assert '812345678' in merged['site_match_evidence']


def test_a_website_from_elsewhere_does_not_inherit_a_foreign_proof():
    """La preuve suit le site. Si la fiche publie le domaine du CSV, elle ne peut
    pas exhiber la preuve obtenue pour un autre domaine."""
    registry = v2.registry_record({'name': 'Konexio', 'siren': '812345678'}, 'z')
    registry.update({'website': 'https://konexio.eu/',
                     'site_match': os_site.SITE_MATCH_SIREN,
                     'site_match_evidence': 'SIREN affiché'})
    csv_row = dict(registry, origin=v2.ORIGIN_CSV, website='https://autre-domaine.fr/',
                   site_match=os_site.SITE_MATCH_NONE, site_match_evidence='', address=None)
    merged = v2.compose_record({'members': [registry, csv_row], 'match': 'siren', 'conflicts': []})
    assert merged['website'] == 'https://autre-domaine.fr/'
    assert merged['site_match'] == os_site.SITE_MATCH_NONE
    assert merged['site_match_evidence'] == ''


def test_the_two_new_steps_are_declared():
    """Une étape mesurée mais non déclarée ne remonterait pas dans le statut
    HTTP : le parcours aurait deux minutes de silence inexpliqué."""
    assert 'site_officiel' in v2.STEP_NAMES
    assert 'crawl_registre' in v2.STEP_NAMES
    assert v2.STEP_NAMES.index('site_officiel') > v2.STEP_NAMES.index('registre')
