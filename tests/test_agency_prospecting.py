"""Garde-fous de la prospection d'agences.

Ces tests figent les quatre règles qui ont manqué le jour où un agent, faute de
trouver des agences, en a inventé deux :

1. le script de prospection écrit dans le dépôt, pas dans un répertoire
   imaginaire (`~/apps/...`) où son travail disparaissait ;
2. une position approximative n'est jamais comptée comme une adresse ;
3. l'adresse connue est affichée — une donnée invisible se fait redécouvrir
   « à la main », c'est-à-dire fabriquer ;
4. chaque outil MCP dit s'il parle d'annonces ou d'entreprises, faute de quoi
   on lance une recherche d'offres en croyant chercher des agences.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_v2():
    """Importe tools/agency_prospecting_v2.py — `tools/` n'est pas un package."""
    path = PROJECT_ROOT / "tools" / "agency_prospecting_v2.py"
    spec = importlib.util.spec_from_file_location("agency_prospecting_v2", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bing_redirects_are_decoded_before_filtering():
    """Bing masque les vrais résultats derrière /ck/a?...&u=a1<base64url>."""
    import base64

    v2 = load_v2()
    target = "https://www.konexio.eu/"
    payload = base64.urlsafe_b64encode(target.encode()).decode().rstrip("=")
    redirect = f"https://www.bing.com/ck/a?x=1&u=a1{payload}&ntb=1"

    assert v2.decode_redirect(redirect) == target
    assert v2._harvest(
        f'<a href="{redirect}">KONEXIO Paris site officiel</a>',
        "https://www.bing.com/",
        "bing",
        "KONEXIO Paris site officiel",
        5,
    ) == [(target, "KONEXIO Paris site officiel", "bing:KONEXIO Paris site officiel")]


def test_site_lookup_ignores_bing_noise_without_query_identity(monkeypatch):
    """Une SERP Bing avec des liens valides mais hors sujet n'est pas une piste."""
    v2 = load_v2()

    monkeypatch.setattr(v2, "search_ddg", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(v2, "search_bing", lambda *_args, **_kwargs: [
        ("https://forums.commentcamarche.net/forum/affich-1", "forum le bon coin", "bing:q"),
        ("https://www.espagne-visite.com/fr/", "Voyage Espagne", "bing:q"),
        ("https://www.konexio.eu/", "KONEXIO - Accueil", "bing:q"),
    ])

    assert v2._site_lookup_search("KONEXIO Paris site officiel") == [
        ("https://www.konexio.eu/", "bing")
    ]


def test_microsoft_help_pages_are_never_engine_candidates():
    v2 = load_v2()

    for host in (
        "go.microsoft.com", "support.microsoft.com", "help.bing.microsoft.com",
        "bing.com", "www.deepl.com", "forums.commentcamarche.net",
    ):
        assert v2.is_bad_host(host)


def test_prospecting_writes_only_inside_the_repository():
    """Régression : les chemins absolus visaient ~/apps/job-search-automation-package.

    C'est le clone du VPS, absent du poste de travail. Le script y tournait, ne
    plantait pas, et n'écrivait nulle part de visible. Un chemin déduit du
    fichier vaut sur les deux machines.
    """
    v2 = load_v2()

    assert v2.ROOT == PROJECT_ROOT
    for name in ("DATA_DIR", "FRONT_DIR", "DEFAULT_OUT_DIR"):
        destination = getattr(v2, name)
        assert destination.is_absolute(), f"{name} doit être absolu"
        assert PROJECT_ROOT in destination.parents or destination == PROJECT_ROOT, (
            f"{name} = {destination} sort du dépôt"
        )


def test_an_approximate_position_is_never_counted_inside_the_radius():
    """« Dans le rayon » doit vouloir dire « adresse lue », pas « ville plausible »."""
    v2 = load_v2()

    results = [
        {"name": "Lue", "address": "6 Villa du Borrégo", "address_source": "site (pages crawlées)", "distance_m": 400},
        {"name": "Devinee", "address": None, "address_source": "~centre paris 20 (approximatif)", "distance_m": 400},
        {"name": "Loin", "address": "1 rue d'ailleurs", "address_source": "site (/contact)", "distance_m": 9000},
        {"name": "Inconnue", "address": None, "address_source": None, "distance_m": None},
    ]

    buckets = v2.partition_by_radius(results, 2000)

    assert [a["name"] for a in buckets["inside"]] == ["Lue"]
    assert [a["name"] for a in buckets["approximate"]] == ["Devinee"]
    assert [a["name"] for a in buckets["outside"]] == ["Loin"]
    assert [a["name"] for a in buckets["unknown"]] == ["Inconnue"]


@pytest.mark.parametrize(
    "address_source,expected",
    [
        ("site (pages crawlées)", "adresse"),
        ("site (/contact)", "contact/legales"),
        ("site (/mentions-legales)", "contact/legales"),
        ("~centre paris 20 (approximatif)", "ville/arr (~centre)"),
        (None, ""),
    ],
)
def test_address_how_says_how_the_position_was_obtained(address_source, expected):
    """`how` est le champ qui empêche de relire une approximation comme une adresse."""
    v2 = load_v2()

    assert v2.address_how({"address_source": address_source}) == expected


def test_postal_code_is_extracted_only_from_a_real_address():
    v2 = load_v2()

    assert v2.postal_code_from_address("401 rue des Pyrénées 75020") == "75020"
    assert v2.postal_code_from_address("Paris 20e") is None
    assert v2.postal_code_from_address(None) is None


def test_curated_csv_enriches_discovered_agencies_without_injecting_old_targets(tmp_path):
    v2 = load_v2()
    csv_path = tmp_path / "companies.csv"
    csv_path.write_text(
        "nom,site,ville,type,statut,poste_vise,adresse,code_postal\n"
        "Agence Test,https://example.test,Paris 75020,agence_web,prioritaire,,1 rue Test 75020,75020\n"
        "Sans site,,Paris 75020,agence_web,a_qualifier,,2 rue Test 75020,75020\n"
        "Ecartee,https://excluded.test,Paris 75020,agence_web,ecartee,,3 rue Test 75020,75020\n",
        encoding="utf-8",
    )
    crawled = [{
        "name": "Nom crawl",
        "website": "https://example.test/",
        "score": 80,
        "sources": ["moteur"],
        "address": None,
    }]

    merged = v2.merge_curated_agencies(crawled, "paris-20", csv_path)

    by_name = {agency["name"]: agency for agency in merged}
    # Le CSV est la voie de correction humaine : c'est son nom qui est publié,
    # mais il ne coûte rien de ce que le crawl a mesuré.
    assert "Nom crawl" not in by_name
    assert by_name["Agence Test"]["score"] == 80
    assert by_name["Agence Test"]["identity_match"] == "domaine"
    assert by_name["Agence Test"]["address"] == "1 rue Test 75020"
    assert by_name["Agence Test"]["postal_code"] == "75020"
    assert "config/companies.csv" in by_name["Agence Test"]["sources"]
    assert "moteur" in by_name["Agence Test"]["sources"]
    assert "Sans site" not in by_name
    assert "Ecartee" not in by_name


def test_paris_20_keeps_only_verified_75020_addresses():
    v2 = load_v2()
    agencies = [
        {"name": "Dans le 20e", "postal_code": "75020"},
        {"name": "Paris voisin", "postal_code": "75019"},
        {"name": "Adresse inconnue", "postal_code": None},
    ]

    kept, rejected = v2.filter_strict_postal_zone(agencies, "paris-20")

    assert [agency["name"] for agency in kept] == ["Dans le 20e"]
    assert {agency["name"] for agency in rejected} == {"Paris voisin", "Adresse inconnue"}


def test_paris_20_uses_only_targeted_queries():
    v2 = load_v2()

    families, queries = v2.queries_for_zone("paris-20")

    assert len(queries) <= 8
    assert all("Paris 20" in query or "75020" in query for query in queries)
    assert set(families) == {"agence", "formation"}


def test_manual_address_survives_a_geocoding_failure(monkeypatch):
    v2 = load_v2()
    monkeypatch.setattr(v2, "geocode", lambda _query: (None, None, ""))
    monkeypatch.setattr(v2, "geocode_ban", lambda _query: (None, None, ""))
    agencies = [{
        "name": "Agence Test",
        "website": "https://example.test",
        "address": "1 rue Test",
        "postal_code": "75020",
        "address_source": "relevé à la main (config/companies.csv)",
        "snippet": "401 rue des Pyrénées 75020",
        "page_texts": [],
    }]

    v2.enrich_with_distances(agencies)

    assert agencies[0]["address"] == "1 rue Test"
    assert agencies[0]["postal_code"] == "75020"
    assert agencies[0]["address_source"] == "relevé à la main (config/companies.csv)"
    assert agencies[0]["distance_m"] is None


def test_two_runs_on_the_same_addresses_reuse_the_cache(monkeypatch, tmp_path):
    """Critère 4 : même adresses, mêmes distances, et plus un seul appel au géocodeur."""
    v2 = load_v2()
    cache_path = tmp_path / "geocode_cache.json"
    calls = []

    def fake_geocode(query):
        calls.append(query)
        return 48.8700, 2.3990, query

    monkeypatch.setattr(v2, "geocode", fake_geocode)
    monkeypatch.setattr(v2, "geocode_ban", lambda _q: (None, None, ""))

    def one_run():
        agencies = [{
            "name": "Agence Test",
            "website": "https://example.test",
            "address": "1 rue Test 75020",
            "postal_code": "75020",
            "address_source": "relevé à la main (config/companies.csv)",
            "snippet": "",
            "page_texts": [],
        }]
        cache = v2.load_geocode_cache(cache_path)
        v2.enrich_with_distances(agencies, cache)
        v2.save_geocode_cache(cache, cache_path)
        return agencies[0]["distance_m"]

    first = one_run()
    after_first = len(calls)
    second = one_run()

    assert first is not None
    assert second == first
    assert len(calls) == after_first, "la deuxième passe a re-géocodé une adresse connue"
    # Le cache est indexé sur l'adresse normalisée : espaces et casse ne créent
    # pas deux entrées pour le même lieu.
    stored = v2.load_geocode_cache(cache_path)
    assert stored, "le cache n'a rien retenu"
    assert all(key == v2.normalized_address(key) for key in stored)


def test_a_geocoding_failure_is_never_cached(monkeypatch, tmp_path):
    """Une coupure d'une minute figerait sinon l'adresse en « position inconnue »."""
    v2 = load_v2()
    monkeypatch.setattr(v2, "geocode", lambda _q: (None, None, ""))
    monkeypatch.setattr(v2, "geocode_ban", lambda _q: (None, None, ""))
    cache: dict = {}

    assert v2.geocode_cached("1 rue Test 75020", cache) == (None, None, "")
    assert cache == {}


def test_published_agencies_never_carry_a_postal_code_without_an_address():
    """Un code postal sans adresse serait une localisation déduite, donc inventée."""
    payload = json.loads(
        (PROJECT_ROOT / "front" / "public" / "data" / "agencies" / "latest.json").read_text(
            encoding="utf-8"
        )
    )

    for agency in payload["agencies"]:
        if not agency.get("address"):
            assert not agency.get("postal_code"), (
                f"{agency.get('name')} porte un code postal sans adresse"
            )


def test_publishable_results_exclude_registry_only_uncertain_candidates():
    """Le registre nourrit le diagnostic, pas les cartes à démarcher.

    Une fiche registre seule n'a ni site officiel vérifié ni auto-description :
    l'afficher comme opportunité produit des "Agences 0/100" sans rapport.
    """
    v2 = load_v2()

    assert not v2.is_publishable_result({
        "name": "KONEXIO",
        "category": "incertain",
        "origin": "registre",
        "origins": ["registre"],
        "website": None,
        "score": 0,
    })
    assert v2.is_publishable_result({"name": "Agence vérifiée", "category": "agence"})
    assert v2.is_publishable_result({"name": "Formation vérifiée", "category": "formation"})


def test_department_registry_uses_one_direct_department_filter():
    v2 = load_v2()
    zone_key = "departement-93-seine-saint-denis"
    v2.DYNAMIC_ZONES[zone_key] = {
        "label": "Seine-Saint-Denis (93)",
        "tier1": ["93", "Seine-Saint-Denis", "93100"],
        "tier2": [],
        "departement": "93",
        "postal_codes": ["93100"],
        "commune_codes": ["93048"],
    }

    class FakeRegistry:
        def __init__(self):
            self.calls = []

        def search(self, **kwargs):
            self.calls.append(kwargs)
            return [{
                "name": "Entreprise 93",
                "siren": "123456789",
                "siret": "12345678900001",
                "legal_address": "1 rue Test 93100 Montreuil",
                "postal_code": "93100",
                "departement": "93",
                "commune_code": "93048",
                "commune_label": "Montreuil",
                "why_candidate": "candidate",
                "sources": ["registre"],
            }]

    registry = FakeRegistry()
    rows, warnings = v2.registry_candidates(zone_key, client=registry)

    assert not warnings
    assert len(rows) == 1
    assert registry.calls[0]["departement"] == "93"
    assert "code_postal" not in registry.calls[0]
    assert rows[0]["departement"] == "93"


def test_department_publishing_contract_keeps_only_verified_levels():
    v2 = load_v2()
    import city_resolver as resolver
    department = {
        "code": "93",
        "name": "Seine-Saint-Denis",
        "postal_codes": ["93100"],
        "commune_codes": ["93048"],
    }

    mention, _ = resolver.locate_in_department(
        {"postal_code": "93100", "how": "", "zone_match": "tier1"}, department
    )
    registry, _ = resolver.locate_in_department(
        {"departement": "93", "how": "siège (registre)", "zone_match": "tier1"}, department
    )

    assert mention not in resolver.PERIMETER_VERIFIED
    assert registry in resolver.PERIMETER_VERIFIED


def test_the_hand_written_csv_obeys_the_same_rule():
    """Même règle à la source qu'à la publication, sinon elle se perd en route.

    `ville` porte déjà « Paris 75020 » : recopier le code postal dans sa propre
    colonne alors qu'aucune adresse n'a été relevée en ferait une donnée
    dérivée, qui se met à diverger et finit par se lire comme un relevé.
    """
    import csv

    with (PROJECT_ROOT / "config" / "companies.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert rows, "config/companies.csv est vide"
    for row in rows:
        if not row["adresse"].strip():
            assert not row["code_postal"].strip(), (
                f"{row['nom']} porte un code postal sans adresse"
            )


def test_company_list_shows_the_address_it_has():
    """Régression : l'adresse existait dans le CSV et n'était affichée nulle part."""
    from hermes_commands.company_top import format_company_list

    text = format_company_list(
        [
            {
                "company": "WEBDIGITAL",
                "url": "https://www.webdigital.fr/",
                "claims": [],
                "opportunity": {
                    "title": "Développeur web",
                    "address": "6 Villa du Borrégo",
                    "postal_code": "75020",
                    "location": "Paris 75020",
                },
            },
            {
                "company": "Livementor",
                "url": "https://livementor.com",
                "claims": [],
                "opportunity": {"title": "Développeur web", "address": "", "postal_code": "", "location": ""},
            },
        ],
        title="Test",
    )

    assert "6 Villa du Borrégo, Paris 75020" in text
    # Rien de connu : on le dit, on ne comble pas le vide.
    assert "Adresse : Non renseignee" in text


def test_every_mcp_tool_says_whether_it_is_about_ads_or_companies():
    """L'agent confondait job_* et company_* et lançait la mauvaise recherche."""
    import hermes_mcp_server

    vague = [
        name
        for name, tool in hermes_mcp_server.TOOLS.items()
        if "ANNONCES" not in tool["description"] and "ENTREPRISES/AGENCES" not in tool["description"]
    ]

    assert vague == [], f"Outils sans domaine annoncé : {vague}"


def test_company_prepare_does_not_generate_a_cv_by_default(monkeypatch):
    import hermes_mcp_server

    monkeypatch.setattr(hermes_mcp_server, "load_cached_companies", lambda: [{"opportunity": {}}])
    captured = {}

    def fake_prepare(number, results, with_cv):
        captured.update(number=number, results=results, with_cv=with_cv)
        return {"company": "Test", "files": {}}

    monkeypatch.setattr(hermes_mcp_server, "prepare_numbered_application", fake_prepare)
    monkeypatch.setattr(hermes_mcp_server, "format_preparation", lambda payload: payload["company"])

    assert hermes_mcp_server.company_prepare({}) == "Test"
    assert captured["with_cv"] is False


# --------------------------------------------------------------------------
# Registre public (API Recherche d'Entreprises)
#
# Toute cette section tourne hors ligne : `opener=` remplace le réseau par la
# fixture. Un test qui appellerait l'API réelle serait vert ou rouge selon la
# météo du jour, et personne ne le relirait.
# --------------------------------------------------------------------------

REGISTRY_FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "agency_registry_montreuil.json"


def load_registry():
    import importlib.util

    path = PROJECT_ROOT / "tools" / "agency_registry.py"
    spec = importlib.util.spec_from_file_location("agency_registry", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_opener():
    """Sert la fixture page par page et compte les appels."""
    pages = json.loads(REGISTRY_FIXTURE.read_text(encoding="utf-8"))["pages"]
    calls = []

    def opener(url, _timeout):
        calls.append(url)
        page = 1
        for part in url.split("?", 1)[-1].split("&"):
            if part.startswith("page="):
                page = int(part.split("=", 1)[1])
        if page > len(pages):
            return json.dumps({"results": [], "total_pages": len(pages), "page": page})
        return json.dumps(pages[page - 1])

    return opener, calls


def test_registry_returns_candidates_never_confirmed_agencies():
    """Critère 1 : identifiants et provenance, mais aucun verdict d'activité.

    Le registre dit qu'une structure est immatriculée en 62.01Z. Il ne dit pas
    qu'elle fait du web : le même code couvre une ESN et un freelance en régie.
    """
    registry = load_registry()
    opener, _calls = fixture_opener()
    client = registry.RegistryClient(opener=opener, sleeper=lambda _s: None, max_pages=5)

    found = client.search(code_postal="93100", naf_codes=registry.NAF_AGENCE)

    by_name = {c["name"]: c for c in found}
    # L'établissement radié (état « C ») n'est pas une cible à démarcher.
    assert "ANCIENNE AGENCE RADIEE" not in by_name
    studio = by_name["STUDIO PYRENEES"]
    assert studio["status"] == "candidate"
    assert studio["siren"] == "900000001"
    assert studio["siret"] == "90000000100017"
    assert studio["sources"] == ["registre:recherche-entreprises"]
    assert "n'est pas prouvée" in studio["why_candidate"]
    # Le registre ne publie pas de site : en deviner un serait l'attribuer.
    assert studio["website"] is None
    for candidate in found:
        assert candidate["status"] == "candidate"


def test_registry_pagination_follows_total_pages_and_stops():
    registry = load_registry()
    opener, calls = fixture_opener()
    client = registry.RegistryClient(opener=opener, sleeper=lambda _s: None, max_pages=5)

    found = client.search(code_postal="93100")

    assert len(calls) == 2, "la fixture annonce total_pages=2 : ni plus, ni moins"
    assert {c["siren"] for c in found} == {"900000001", "900000002", "900000004"}


def test_registry_rate_limit_is_respected_between_calls():
    """Dépasser la cadence annoncée ferait tomber le registre pour tout le monde."""
    registry = load_registry()
    opener, _calls = fixture_opener()
    slept, now = [], [0.0]
    client = registry.RegistryClient(
        opener=opener,
        sleeper=slept.append,
        clock=lambda: now[0],
        max_calls_per_second=5,
        max_pages=5,
    )

    client.search(code_postal="93100")

    assert slept, "aucune pause entre deux appels consécutifs"
    assert all(pause == pytest.approx(0.2) for pause in slept)


def test_a_non_diffusible_establishment_keeps_an_absent_address():
    """Critère 5 : une adresse absente du registre reste absente.

    Le registre masque les structures non diffusibles au lieu de les omettre.
    Compléter l'adresse à partir de la commune produirait une adresse fabriquée
    et parfaitement crédible.
    """
    registry = load_registry()
    opener, _calls = fixture_opener()
    client = registry.RegistryClient(opener=opener, sleeper=lambda _s: None, max_pages=5)

    masked = next(c for c in client.search(code_postal="93100") if c["siren"] == "900000002")

    assert masked["diffusible"] is False
    assert masked["legal_address"] is None
    assert masked["legal_address_source"] is None
    assert masked["postal_code"] is None
    assert masked["commune_label"] == "MONTREUIL"


def test_a_registry_outage_raises_instead_of_returning_nothing():
    """Une liste vide se relit « il n'y a rien ici » : c'est ce vide qui a fait inventer."""
    from urllib.error import HTTPError, URLError

    registry = load_registry()

    def quota(url, _timeout):
        raise HTTPError(url, 429, "Too Many Requests", {}, None)

    def offline(_url, _timeout):
        raise URLError("nom de domaine introuvable")

    for opener, fragment in ((quota, "429"), (offline, "injoignable")):
        client = registry.RegistryClient(opener=opener, sleeper=lambda _s: None)
        with pytest.raises(registry.RegistryError) as raised:
            client.search(code_postal="93100")
        assert fragment in str(raised.value)


def test_a_registry_outage_does_not_erase_the_crawl_results(monkeypatch):
    """Critère 5 : le registre tombe, le crawl web continue seul et on le dit."""
    v2 = load_v2()

    def boom(*_args, **_kwargs):
        raise v2.RegistryError("registre : quota de requêtes dépassé (HTTP 429)")

    monkeypatch.setattr(v2, "search_zone_candidates", boom)

    rows, warnings = v2.registry_candidates("paris-20")

    assert rows == []
    assert warnings and "le crawl web continue seul" in warnings[0]


def test_a_zone_without_an_explicit_postal_code_is_not_guessed():
    """Deviner les communes d'« ile-de-france » choisirait le périmètre à notre place."""
    v2 = load_v2()

    rows, warnings = v2.registry_candidates("ile-de-france")

    assert rows == []
    assert warnings and "aucun code postal explicite" in warnings[0]
    assert v2.postal_codes_of(["paris 20", "belleville", "75020"]) == ["75020"]


# --------------------------------------------------------------------------
# Fusion des trois sources et identité
# --------------------------------------------------------------------------


def test_the_same_establishment_from_three_sources_makes_one_entry():
    """Critère 3 : registre + crawl + CSV se rejoignent sur une seule fiche."""
    v2 = load_v2()

    merged = v2.merge_records([
        {"name": "Nom crawl", "website": "https://studio-pyrenees.fr/", "siren": "900000001",
         "origin": v2.ORIGIN_WEB, "score": 72, "sources": ["moteur"]},
        {"name": "STUDIO PYRENEES", "website": None, "siren": "900000001",
         "siret": "90000000100017", "origin": v2.ORIGIN_REGISTRY,
         "legal_address": "14 Rue de Paris 93100 Montreuil",
         "legal_address_source": "registre (Sirene/RNE via API Recherche d'Entreprises)",
         "sources": ["registre:recherche-entreprises"]},
        {"name": "Studio Pyrénées", "website": "https://studio-pyrenees.fr", "siren": "900000001",
         "origin": v2.ORIGIN_CSV, "address": "14 villa du Borrégo", "postal_code": "93100",
         "address_source": "relevé à la main (config/companies.csv)",
         "sources": ["config/companies.csv"]},
    ])

    assert len(merged) == 1
    record = merged[0]
    assert record["identity_match"] == "siren"
    assert sorted(record["origins"]) == ["csv", "registre", "web"]
    assert record["score"] == 72                       # le crawl garde sa mesure
    assert record["name"] == "Studio Pyrénées"         # le CSV garde la main
    assert record["address"] == "14 villa du Borrégo"  # relevé humain > registre
    assert record["legal_address"] == "14 Rue de Paris 93100 Montreuil"
    assert record["identity_candidates"] == []


def test_an_uncertain_name_match_invents_no_domain_and_no_siren():
    """Critère 3 : deux « Studio Bleu » normalisés pareil peuvent être deux sociétés."""
    v2 = load_v2()

    merged = v2.merge_records([
        {"name": "Studio Bleu", "website": "https://studiobleu.fr/", "origin": v2.ORIGIN_WEB,
         "score": 60, "sources": ["moteur"]},
        {"name": "STUDIO BLEU", "website": None, "siren": "900000009",
         "siret": "90000000900011", "origin": v2.ORIGIN_REGISTRY,
         "legal_address": "3 Rue Inconnue 93100 Montreuil",
         "legal_address_source": "registre (Sirene/RNE via API Recherche d'Entreprises)",
         "sources": ["registre:recherche-entreprises"]},
    ])

    assert len(merged) == 1
    record = merged[0]
    assert record["identity_match"] == v2.UNCERTAIN_IDENTITY
    # Rien du registre ne monte dans la fiche : le rapprochement n'est pas prouvé.
    assert record["siren"] is None
    assert record["siret"] is None
    assert record["legal_address"] is None
    # Mais rien n'est perdu non plus : le rapprochement possible reste nommé.
    assert record["identity_candidates"][0]["siren"] == "900000009"
    assert "non confirmé" in record["identity_candidates"][0]["source"]


def test_an_identity_conflict_is_named_instead_of_being_resolved():
    """Deux clés d'une fiche pointant vers deux groupes : fusionner serait trancher."""
    v2 = load_v2()

    merged = v2.merge_records([
        {"name": "Studio Alpha", "website": "https://alpha.example/", "origin": v2.ORIGIN_WEB,
         "score": 60, "sources": ["moteur"]},
        {"name": "Studio Beta", "website": "https://beta.example/", "origin": v2.ORIGIN_WEB,
         "score": 55, "sources": ["moteur"]},
        # Le registre dit « Studio Beta », mais le SIREN est déjà pris par Alpha.
        {"name": "Studio Beta", "website": "https://alpha.example/", "siren": "900000007",
         "origin": v2.ORIGIN_REGISTRY, "sources": ["registre:recherche-entreprises"]},
    ])

    conflicts = [c for record in merged for c in record["identity_conflicts"]]
    assert conflicts, "le conflit d'identité a été résolu en silence"
    assert len(merged) == 2, "deux structures distinctes ont été fondues en une"


def test_a_registry_only_candidate_never_receives_a_website():
    """Critère 1/2 : sans site, pas de verdict — le registre ne prouve pas l'activité."""
    v2 = load_v2()

    record = v2.registry_record(
        {"name": "STUDIO PYRENEES", "siren": "900000001", "siret": "90000000100017",
         "activity_code": "62.01Z", "legal_address": "14 Rue de Paris 93100 Montreuil",
         "commune_label": "MONTREUIL", "postal_code": "93100",
         "why_candidate": "code APE 62.01Z relevé au registre — l'activité réelle n'est pas prouvée",
         "sources": ["registre:recherche-entreprises"]},
        "paris-20",
    )

    assert record["website"] is None
    assert record["category"] == "incertain"


# --------------------------------------------------------------------------
# Verdict d'activité : ce que la structure dit d'elle-même
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,parts,expected",
    [
        ("Access42", ["Access42 — expertise et formations en accessibilité numérique",
                      "Nous proposons une formation en accessibilité web (RGAA)."], "formation"),
        ("Simplon", ["Simplon.co, organisme de formation aux métiers du numérique"], "formation"),
        ("Agence web", ["Studio Mezzo — agence web à Paris",
                        "Création de sites sur mesure. Nos réalisations."], "agence"),
        ("Webflow", ["Webflow — le site web sans coder",
                     "Commencez votre essai gratuit dès aujourd'hui."], "ecarte"),
        ("Annuaire", ["Comparez les agences web et trouvez un prestataire",
                      "Annuaire des agences digitales"], "ecarte"),
        ("Sans texte", [""], "incertain"),
    ],
)
def test_the_activity_verdict_comes_from_the_self_description(label, parts, expected):
    """Critère 2/6 : ni le code APE ni le score ne rendent ce verdict."""
    from company_analysis.verifier import classify_self_description

    verdict = classify_self_description(parts)

    assert verdict["category"] == expected, f"{label} : {verdict['reason']}"
    if expected in ("agence", "formation"):
        assert verdict["evidence"], f"{label} classé sans citation"


def test_an_unreadable_self_description_is_uncertain_never_excluded():
    """Une donnée manquante produit `incertain` : un écarté disparaît, pas un incertain."""
    from company_analysis.verifier import classify_self_description

    assert classify_self_description([])["category"] == "incertain"
    assert classify_self_description(["Bienvenue sur notre site."])["category"] == "incertain"


def test_the_registry_never_produces_an_activity_claim():
    """Le Vérificateur ne peut pas fabriquer un constat d'activité depuis le registre."""
    from company_analysis.verifier import build_claims

    claims = build_claims(
        {"nom": "Studio Pyrénées"},
        {
            "registry_lookup": {
                "value": {
                    "siren": "900000001",
                    "legal_address": "14 Rue de Paris 93100 Montreuil",
                },
                "evidence": "registre (Sirene/RNE) — SIREN 900000001",
            }
        },
    )
    registry_claims = [c for c in claims if str(c["check"].get("kind", "")).startswith("registry_")]

    assert registry_claims, "les mesures du registre n'ont produit aucun constat"
    assert {c["category"] for c in registry_claims} == {"identity", "legal_address"}
    # Le code APE est dans la mesure et n'est jamais reformulé en activité :
    # « 62.01Z » publié comme « agence web » est exactement l'invention à éviter.
    assert all(c["category"] != "activity" for c in registry_claims)


# --------------------------------------------------------------------------
# Barème déterministe
# --------------------------------------------------------------------------


def test_international_does_not_validate_the_nation_zone():
    """Critère 6 : « international » contenait « nation », et validait Nation."""
    v2 = load_v2()

    assert v2.has_term("agence nation paris 20", "nation") is True
    assert v2.has_term("une agence internationale", "nation") is False
    assert v2.zone_of("agence internationale de conseil", "paris-20")[0] == "none"


def test_platforms_and_directories_are_excluded():
    """Critère 6 : ce ne sont pas des employeurs, ce sont des outils et des listes."""
    v2 = load_v2()

    for base, name, text in (
        ("https://webflow.com/", "Webflow", "Créez un site sans coder, essai gratuit."),
        ("https://livementor.com/", "Livementor", "Nos formations en ligne."),
    ):
        scored = v2.score_candidate(name, base, text, [], "paris-20")
        assert scored["category"] == "ecarte", f"{name} : {scored['category_reason']}"

    annuaire = v2.score_candidate(
        "Annuaire des agences",
        "https://lesagences.example/",
        "Annuaire : comparez les agences web et trouvez un prestataire près de chez vous.",
        [],
        "paris-20",
    )
    assert annuaire["category"] == "ecarte"


def test_a_verified_formation_is_never_excluded_for_not_being_an_agency():
    """Critère 6 : le formateur est une cible, pas un faux positif à éliminer."""
    v2 = load_v2()

    for name, base, text in (
        ("Access42", "https://access42.net/",
         "Access42 : expertise et formations en accessibilité numérique. "
         "Formation en RGAA, audits WCAG, à Paris 20e."),
        ("Simplon", "https://simplon.co/",
         "Simplon.co, organisme de formation aux métiers du numérique. "
         "Formation développeur web à Paris 20e, titre professionnel RNCP."),
    ):
        scored = v2.score_candidate(name, base, text, [], "paris-20")
        assert scored["category"] == "formation", f"{name} : {scored['category_reason']}"
        assert scored["formation_org"] is True
        # Le score classe, il n'élimine pas : un formateur au vocabulaire
        # d'agence pauvre reste une cible, pas un écarté.
        assert scored["signals"]["exclusion"] == []
        assert v2.keeps_candidate(scored) is True, f"{name} tombe hors du résultat"


def test_a_redundant_signal_family_no_longer_saturates_the_score():
    """Critère 6 : répéter « WordPress » vingt fois ne vaut pas une agence parfaite."""
    v2 = load_v2()

    spam = v2.score_candidate(
        "Studio Spam",
        "https://spam.example/",
        " ".join(["wordpress woocommerce php symfony drupal shopify react vue nuxt"] * 30),
        [],
        "",
    )

    assert spam["family_scores"]["stack"] <= v2.FAMILY_CAPS["stack"]
    assert spam["score"] < 100, "le barème sature encore sur une seule famille"

    # Agence et formation sont plafonnées séparément : un site qui répète le
    # vocabulaire des deux ne devient pas parfait pour autant.
    both = v2.score_candidate(
        "Studio Double",
        "https://double.example/",
        " ".join(["agence web création de site formation professionnelle qualiopi"] * 30),
        [],
        "",
    )
    for family, cap in v2.FAMILY_CAPS.items():
        assert both["family_scores"][family] <= cap, f"famille {family} non plafonnée"
    # Le détail reste lisible : un score sans ses signaux ne se relit pas.
    assert set(both["signals"]) == {"positive", "negative", "exclusion"}
    assert both["signals"]["positive"]


def test_search_task_deduplication_includes_zone_and_radius():
    script = """
      import { sameProspectingRequest } from './server/services/agenciesService.js';
      const task = { zone: 'paris-20', radius_m: 2000 };
      const result = [
        sameProspectingRequest(task, { zone: 'paris-20', radiusM: 2000 }),
        sameProspectingRequest(task, { zone: 'ile-de-france', radiusM: 2000 }),
        sameProspectingRequest(task, { zone: 'paris-20', radiusM: 3000 }),
      ];
      console.log(JSON.stringify(result));
    """
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == [True, False, False]


# ── Historique par recherche (phase 3) ───────────────────────────────────────


def _search_payload(search_id, zone, label, generated_at, agencies, radius_m=None):
    return {
        "ok": True,
        "version": "v2",
        "search_id": search_id,
        "zone": zone,
        "zone_label": label,
        "generated_at": generated_at,
        "distance_origin": "21 Rue Monte-Cristo, 75020 Paris",
        "radius": {"radius_m": radius_m} if radius_m else {},
        "agencies": agencies,
    }


def test_two_searches_coexist_and_the_second_becomes_latest(tmp_path):
    """Régression : `latest.json` était la seule mémoire, un run Lille effaçait Montreuil."""
    v2 = load_v2()

    montreuil = _search_payload(
        "montreuil-20260922-010000", "montreuil", "Montreuil", "2026-09-22T01:00:00",
        [{"name": "Studio M", "website": "https://studio-m.fr", "how": "adresse", "category": "agence"}],
        radius_m=2000,
    )
    lille = _search_payload(
        "lille-20260922-020000", "lille", "Lille", "2026-09-22T02:00:00",
        [{"name": "Studio L", "website": "https://studio-l.fr", "how": "ville/arr (~centre)", "category": "formation"}],
    )

    v2.publish_search(montreuil, tmp_path)
    result = v2.publish_search(lille, tmp_path)

    searches_dir = tmp_path / v2.SEARCHES_DIRNAME
    assert (searches_dir / "montreuil-20260922-010000.json").exists()
    assert (searches_dir / "lille-20260922-020000.json").exists()

    # Le premier fichier n'a pas bougé : c'est ce que « snapshot immuable » veut dire.
    kept = json.loads((searches_dir / "montreuil-20260922-010000.json").read_text(encoding="utf-8"))
    assert kept["agencies"][0]["name"] == "Studio M"

    latest = json.loads((tmp_path / v2.LATEST_NAME).read_text(encoding="utf-8"))
    assert latest["search_id"] == "lille-20260922-020000"
    assert result["latest_updated"] is True

    index = json.loads((tmp_path / v2.SEARCH_INDEX_NAME).read_text(encoding="utf-8"))
    assert index["latest_search_id"] == "lille-20260922-020000"
    # Le plus récent d'abord : le sélecteur n'a pas à trier lui-même.
    assert [s["search_id"] for s in index["searches"]] == [
        "lille-20260922-020000",
        "montreuil-20260922-010000",
    ]


def test_the_index_never_counts_an_approximate_position_as_a_known_address(tmp_path):
    """Même règle que le rayon : un centre d'arrondissement n'est pas une adresse."""
    v2 = load_v2()

    payload = _search_payload(
        "paris-20-20260922-030000", "paris-20", "Paris 20e", "2026-09-22T03:00:00",
        [
            {"name": "Lue", "website": "https://a.fr", "how": "adresse", "category": "agence"},
            {"name": "Legales", "website": "https://b.fr", "how": "contact/legales", "category": "agence"},
            {"name": "Devinee", "website": "https://c.fr", "how": "ville/arr (~centre)", "category": "formation"},
            {"name": "Siege", "website": "https://d.fr", "how": "siège (registre)", "category": "agence"},
        ],
    )
    v2.publish_search(payload, tmp_path)

    entry = json.loads((tmp_path / v2.SEARCH_INDEX_NAME).read_text(encoding="utf-8"))["searches"][0]
    assert entry["address_known"] == 2
    assert entry["categories"] == {"agence": 3, "formation": 1}


def test_an_empty_search_is_recorded_without_destroying_the_previous_one(tmp_path):
    """Une passe vide est un fait ; elle ne remplace pas un historique utile."""
    v2 = load_v2()

    full = _search_payload(
        "montreuil-20260922-010000", "montreuil", "Montreuil", "2026-09-22T01:00:00",
        [{"name": "Studio M", "website": "https://studio-m.fr", "how": "adresse", "category": "agence"}],
    )
    v2.publish_search(full, tmp_path)

    empty = _search_payload(
        "lille-20260922-020000", "lille", "Lille", "2026-09-22T02:00:00", [],
    )
    result = v2.publish_search(empty, tmp_path)

    assert result["state"] == "vide"
    assert result["latest_updated"] is True
    # latest.json reflète aussi une passe vide : sinon l'UI ressuscite les faux positifs précédents.
    assert result["latest_search_id"] == "lille-20260922-020000"
    latest = json.loads((tmp_path / v2.LATEST_NAME).read_text(encoding="utf-8"))
    assert latest["search_id"] == "lille-20260922-020000"
    assert latest["agencies"] == []

    # La passe vide est consultable : son absence se relirait « pas de run ».
    assert (tmp_path / v2.SEARCHES_DIRNAME / "lille-20260922-020000.json").exists()
    index = json.loads((tmp_path / v2.SEARCH_INDEX_NAME).read_text(encoding="utf-8"))
    states = {s["search_id"]: s["state"] for s in index["searches"]}
    assert states == {"lille-20260922-020000": "vide", "montreuil-20260922-010000": "ok"}


def test_retention_never_deletes_a_pinned_or_published_search(tmp_path):
    """Une suppression est annoncée ; une recherche épinglée n'est jamais touchée."""
    v2 = load_v2()

    for hour in range(1, 5):
        v2.publish_search(
            _search_payload(
                f"z{hour}-2026092{hour}-000000", f"z{hour}", f"Zone {hour}",
                f"2026-09-2{hour}T00:00:00",
                [{"name": f"A{hour}", "website": f"https://a{hour}.fr", "how": "adresse", "category": "agence"}],
            ),
            tmp_path,
        )

    # La plus ancienne est épinglée à la main, comme le ferait l'utilisateur.
    index_path = tmp_path / v2.SEARCH_INDEX_NAME
    index = json.loads(index_path.read_text(encoding="utf-8"))
    for search in index["searches"]:
        if search["search_id"] == "z1-20260921-000000":
            search["pinned"] = True
    index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")

    result = v2.publish_search(
        _search_payload(
            "z5-20260925-000000", "z5", "Zone 5", "2026-09-25T00:00:00",
            [{"name": "A5", "website": "https://a5.fr", "how": "adresse", "category": "agence"}],
        ),
        tmp_path,
        retention=2,
    )

    survivors = [s["search_id"] for s in json.loads(index_path.read_text(encoding="utf-8"))["searches"]]
    assert "z5-20260925-000000" in survivors, "la passe publiée ne peut pas être élaguée"
    assert "z1-20260921-000000" in survivors, "une recherche épinglée n'est jamais supprimée"
    assert result["pruned"], "une rétention qui supprime doit le dire"
    for pruned in result["pruned"]:
        assert not (tmp_path / v2.SEARCHES_DIRNAME / f"{pruned}.json").exists()
        assert pruned not in survivors


def test_a_corrupted_index_does_not_lose_the_search_being_published(tmp_path):
    v2 = load_v2()

    (tmp_path / v2.SEARCH_INDEX_NAME).write_text("{ pas du json", encoding="utf-8")
    result = v2.publish_search(
        _search_payload(
            "paris-20-20260922-040000", "paris-20", "Paris 20e", "2026-09-22T04:00:00",
            [{"name": "A", "website": "https://a.fr", "how": "adresse", "category": "agence"}],
        ),
        tmp_path,
    )

    assert result["state"] == "ok"
    index = json.loads((tmp_path / v2.SEARCH_INDEX_NAME).read_text(encoding="utf-8"))
    assert [s["search_id"] for s in index["searches"]] == ["paris-20-20260922-040000"]


def test_a_search_id_is_a_safe_filename_derived_from_the_zone():
    v2 = load_v2()

    assert v2.make_search_id("paris-20", "20260922-010000") == "paris-20-20260922-010000"
    # Une zone exotique ne doit jamais produire un chemin : ni `/`, ni `..`.
    forged = v2.make_search_id("../../etc/passwd", "20260922-010000")
    assert "/" not in forged and ".." not in forged
    assert v2.make_search_id("", "20260922-010000").startswith("zone-")


def test_publishing_without_a_search_id_is_refused(tmp_path):
    """Sans identifiant, une passe écraserait la précédente sans le dire."""
    v2 = load_v2()

    with pytest.raises(ValueError):
        v2.publish_search({"agencies": []}, tmp_path)


def test_the_server_reads_the_selected_search_and_names_the_unknown_ones(tmp_path):
    """Le ciblage doit lire le fichier de la recherche affichée, pas « la plus récente »."""
    script = """
      import { readSearchIndex, readSearchPayload } from './server/services/agenciesService.js';
      const index = readSearchIndex();
      const out = { source: index.source, count: index.searches.length };
      out.latest = readSearchPayload(null).search_id;
      try {
        readSearchPayload('recherche-fantome-20260101-000000');
        out.unknown = 'ACCEPTE';
      } catch (err) {
        out.unknown = err.message;
      }
      try {
        readSearchPayload('../../../etc/passwd');
        out.traversal = 'ACCEPTE';
      } catch (err) {
        out.traversal = 'REFUSE';
      }
      console.log(JSON.stringify(out));
    """
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    out = json.loads(completed.stdout)

    assert out["count"] >= 1, "une installation avec latest.json doit exposer au moins une recherche"
    assert out["latest"], "l'alias de compatibilité doit rester lisible"
    # Un identifiant inconnu est refusé en nommant ce qui existe : une liste vide
    # se relirait « il n'y a rien », et c'est ce qui a fait inventer des agences.
    assert "Recherche inconnue" in out["unknown"]
    assert "Recherches disponibles" in out["unknown"]
    assert out["traversal"] == "REFUSE"
