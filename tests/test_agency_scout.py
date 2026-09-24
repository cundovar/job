"""Tests Agency Scout : découverte Places (API simulée), rayon, plafond, validation IA."""

import pytest

from agency_scout import core


PLACES = {"places": [
    {"id": "near", "displayName": {"text": "Agence Proche"}, "formattedAddress": "10 rue X, 75020 Paris",
     "addressComponents": [{"longText": "75020", "types": ["postal_code"]}],
     "location": {"latitude": 48.8560, "longitude": 2.3990}, "websiteUri": "https://www.proche.fr/"},
    {"id": "voisin", "displayName": {"text": "Agence Voisine"}, "formattedAddress": "2 rue Y, 75019 Paris",
     "addressComponents": [{"longText": "75019", "types": ["postal_code"]}],
     "location": {"latitude": 48.8561, "longitude": 2.3991}, "websiteUri": "https://voisin.fr"},
    {"id": "exote", "displayName": {"text": "Agence Exotique"}, "formattedAddress": "99 rue Z, 75020 Paris",
     "addressComponents": [{"longText": "75020", "types": ["postal_code"]}],
     "location": {"latitude": 48.80, "longitude": 2.30}, "websiteUri": "https://exote.fr"},
    {"id": "far", "displayName": {"text": "Agence Loin"}, "formattedAddress": "Lyon",
     "location": {"latitude": 45.76, "longitude": 4.83}, "websiteUri": "https://loin.fr"},
    {"id": "nosite", "displayName": {"text": "Sans Site"}, "formattedAddress": "75020 Paris",
     "addressComponents": [{"longText": "75020", "types": ["postal_code"]}],
     "location": {"latitude": 48.8554, "longitude": 2.3985}},
]}


@pytest.fixture
def db(tmp_path, monkeypatch):
    # Le client Places est partagé avec la V2 (tools/google_places.py) :
    # on simule la primitive brute au niveau du module scout.
    def fake_places_search(query, api_key, *, opener=None, timeout=15,
                           location_bias=None, page_size=None, max_pages=1,
                           on_request=None):
        assert location_bias is not None, "discover doit passer le biais de localisation"
        if on_request:
            on_request()
        return PLACES["places"]

    monkeypatch.setattr(core, "places_text_search", fake_places_search)
    conn = core.connect(tmp_path / "t.db")
    yield conn
    conn.close()


def test_discover_keeps_only_places_inside_radius(db):
    ids = core.discover(db, ["agence web"], (48.85536, 2.39845), 3000, "key")
    assert set(ids) == {"near", "voisin", "nosite"}  # le rayon seul décide, le CP est ignoré
    row = db.execute("SELECT * FROM agencies WHERE place_id='near'").fetchone()
    assert row["domain"] == "proche.fr" and row["distance_m"] < 100


def test_postal_mode_admits_by_code_postal_not_radius(db):
    ids = core.discover(db, ["agence web"], (48.85536, 2.39845), 3000, "key",
                        postal_codes={"75020"})
    # voisin (75019, tout proche) rejeté ; exote (75020, hors rayon) gardé.
    assert set(ids) == {"near", "exote", "nosite"}


def test_monthly_cap_is_a_hard_stop(db, monkeypatch):
    monkeypatch.setattr(core, "MONTHLY_CAP", 1)
    core.search_places(db, "q", (48.85, 2.39), 1000, "key")
    with pytest.raises(core.QuotaReached):
        core.search_places(db, "q", (48.85, 2.39), 1000, "key")


def test_invalid_llm_output_is_stored_as_error(monkeypatch):
    monkeypatch.setattr(core, "fetch_site_text",
                        lambda url: ("Nous créons des sites web pour nos clients. " * 5, [url], [], ""))
    monkeypatch.setattr(core, "llm_complete", lambda s, u: ({"categorie": "boulangerie", "score": 42}, "fake"))
    result = core.analyze("x.fr", "https://x.fr", None, "sys")
    assert result["error"].startswith("analyse IA invalide")


def test_invented_proof_is_flagged(monkeypatch):
    monkeypatch.setattr(core, "fetch_site_text",
                        lambda url: ("Nous créons des sites web pour nos clients. " * 5, [url], [], ""))
    monkeypatch.setattr(core, "llm_complete", lambda s, u: (
        {"categorie": "agence", "score": 7, "resume": "ok", "preuve": "Leader européen du WordPress headless"}, "fake"))
    assert core.analyze("x.fr", "https://x.fr", None, "sys")["preuve_ok"] == 0


def test_emails_from_site_fetch_are_stored(monkeypatch):
    monkeypatch.setattr(core, "fetch_site_text",
                        lambda url: ("Nous créons des sites web pour nos clients. " * 5, [url], ["contact@agence.fr"], ""))
    monkeypatch.setattr(core, "llm_complete", lambda s, u: (
        {"categorie": "agence", "score": 6, "resume": "ok", "preuve": "Nous créons des sites web pour nos clients"}, "fake"))
    result = core.analyze("y.fr", "https://y.fr", None, "sys")
    assert result["emails"] == ["contact@agence.fr"]


# ── Ajout manuel : une URL, la même analyse, la même base ─────────────────

TEXTE_SITE = "Nous formons des adultes au numérique et au développement web. " * 4

VERDICT = {"categorie": "formation", "score": 8, "resume": "Organisme de formation.",
           "preuve": "Nous formons des adultes au numérique"}


@pytest.fixture
def base(tmp_path, monkeypatch):
    """Base vide + IA simulée : l'ajout manuel ne touche jamais le réseau ici."""
    monkeypatch.setattr(core, "llm_complete", lambda s, u: (dict(VERDICT), "fake"))
    monkeypatch.setattr(core, "_profile_summary", lambda: "profil de test")
    return tmp_path / "scout.db"


def _fetch(texte=TEXTE_SITE, nom="Organisme Test", url_finale=None):
    return lambda url: (texte, [url_finale or url], ["contact@organisme.fr"], nom)


def test_ajout_manuel_cree_la_fiche_et_son_analyse(base, monkeypatch):
    monkeypatch.setattr(core, "fetch_site_text", _fetch())

    result = core.add_agency("organisme-test.fr", path=base)

    assert result["ok"] and result["already_known"] is False
    assert result["domain"] == "organisme-test.fr"
    assert (result["categorie"], result["score"]) == ("formation", 8)

    listing = core.list_agencies(path=base)["agencies"]
    assert len(listing) == 1
    fiche = listing[0]
    assert fiche["source"] == "manuel"
    assert fiche["place_id"] == "manuel:organisme-test.fr"
    assert fiche["name"] == "Organisme Test"
    # Aucune adresse inventée : la saisie manuelle n'en fournit pas.
    assert fiche["address"] is None and fiche["distance_m"] is None


def test_le_nom_saisi_prime_sur_celui_lu_sur_le_site(base, monkeypatch):
    monkeypatch.setattr(core, "fetch_site_text", _fetch(nom="Titre SEO à rallonge"))

    result = core.add_agency("https://organisme-test.fr", name="Organisme Test", path=base)

    assert result["name"] == "Organisme Test"


def test_le_site_retenu_est_l_url_finale_pas_le_domaine(base, monkeypatch):
    """Un certificat peut ne couvrir que www : on garde l'URL réellement lue."""
    monkeypatch.setattr(core, "fetch_site_text", _fetch(url_finale="https://www.organisme-test.fr/accueil"))

    core.add_agency("organisme-test.fr", path=base)

    assert core.list_agencies(path=base)["agencies"][0]["website"] == "https://www.organisme-test.fr/accueil"


def test_un_site_injoignable_cree_la_fiche_avec_son_erreur(base, monkeypatch):
    def boom(url):
        raise RuntimeError("Connection refused")

    monkeypatch.setattr(core, "fetch_site_text", boom)

    result = core.add_agency("injoignable-test.fr", path=base)

    # Pas d'exception, pas de faux échec : la fiche existe, l'erreur est dite.
    assert result["ok"] and result["error"].startswith("site illisible")
    fiche = core.list_agencies(path=base)["agencies"][0]
    assert fiche["domain"] == "injoignable-test.fr"
    assert fiche["categorie"] is None


def test_un_domaine_deja_connu_n_est_pas_duplique(base, monkeypatch):
    monkeypatch.setattr(core, "fetch_site_text", _fetch())
    db = core.connect(base)
    db.execute(
        """INSERT INTO agencies (place_id, name, address, lat, lng, distance_m, website, domain,
                                 types, query, first_seen, last_seen, source)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("places-42", "Vu par Google", "10 rue X, 75020 Paris", 48.85, 2.39, 120,
         "https://organisme-test.fr", "organisme-test.fr", "", "agence web",
         core.now(), core.now(), "places"),
    )
    db.commit()
    db.close()

    result = core.add_agency("organisme-test.fr", path=base)

    assert result["already_known"] is True and result["source"] == "places"
    listing = core.list_agencies(path=base)["agencies"]
    assert len(listing) == 1 and listing[0]["name"] == "Vu par Google"


@pytest.mark.parametrize("url", ["", "ftp://organisme.fr", "http://localhost:8000",
                                 "http://192.168.1.10", "pas-une-url"])
def test_une_url_non_publique_est_refusee(base, url):
    with pytest.raises(ValueError):
        core.add_agency(url, path=base)


# --- Filtrage par arrondissement / commune ------------------------------------
# Le front regroupe sur ces deux champs. Ils sont **lus** dans l'adresse Google :
# une fiche sans adresse ne se range dans aucun arrondissement, et c'est une
# information, pas un trou à combler.

@pytest.mark.parametrize("adresse,attendu", [
    ("10 rue X, 75020 Paris, France", ("75020", "Paris")),
    ("75011 Paris", ("75011", "Paris")),
    ("2 av. Y, 93100 Montreuil, France", ("93100", "Montreuil")),
    ("12 rue Z, 69003 Lyon 3e", ("69003", "Lyon 3e")),
    ("Lyon", (None, None)),
    ("", (None, None)),
    (None, (None, None)),
])
def test_le_code_postal_et_la_commune_sont_lus_dans_l_adresse(adresse, attendu):
    assert core.address_parts(adresse) == attendu


def test_list_agencies_expose_le_code_postal_et_la_commune(base, monkeypatch):
    db = core.connect(base)
    db.execute(
        """INSERT INTO agencies (place_id, name, address, lat, lng, distance_m, website, domain,
                                 types, query, first_seen, last_seen, source)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("places-1", "Agence Vingtième", "10 rue X, 75020 Paris, France", 48.86, 2.39, 200,
         "https://vingtieme.fr", "vingtieme.fr", "", "agence web",
         core.now(), core.now(), "places"),
    )
    db.commit()
    db.close()
    monkeypatch.setattr(core, "fetch_site_text", _fetch())
    core.add_agency("https://sans-adresse.fr", path=base)  # saisie manuelle : adresse NULL

    par_domaine = {a["domain"]: a for a in core.list_agencies(path=base)["agencies"]}

    assert (par_domaine["vingtieme.fr"]["code_postal"], par_domaine["vingtieme.fr"]["ville"]) == ("75020", "Paris")
    assert par_domaine["sans-adresse.fr"]["code_postal"] is None
    assert par_domaine["sans-adresse.fr"]["ville"] is None
