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
                        lambda url: ("Nous créons des sites web pour nos clients. " * 5, [url], []))
    monkeypatch.setattr(core, "llm_complete", lambda s, u: ({"categorie": "boulangerie", "score": 42}, "fake"))
    result = core.analyze("x.fr", "https://x.fr", None, "sys")
    assert result["error"].startswith("analyse IA invalide")


def test_invented_proof_is_flagged(monkeypatch):
    monkeypatch.setattr(core, "fetch_site_text",
                        lambda url: ("Nous créons des sites web pour nos clients. " * 5, [url], []))
    monkeypatch.setattr(core, "llm_complete", lambda s, u: (
        {"categorie": "agence", "score": 7, "resume": "ok", "preuve": "Leader européen du WordPress headless"}, "fake"))
    assert core.analyze("x.fr", "https://x.fr", None, "sys")["preuve_ok"] == 0


def test_emails_from_site_fetch_are_stored(monkeypatch):
    monkeypatch.setattr(core, "fetch_site_text",
                        lambda url: ("Nous créons des sites web pour nos clients. " * 5, [url], ["contact@agence.fr"]))
    monkeypatch.setattr(core, "llm_complete", lambda s, u: (
        {"categorie": "agence", "score": 6, "resume": "ok", "preuve": "Nous créons des sites web pour nos clients"}, "fake"))
    result = core.analyze("y.fr", "https://y.fr", None, "sys")
    assert result["emails"] == ["contact@agence.fr"]
