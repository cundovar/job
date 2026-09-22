"""Tests Agency Scout : découverte Places (API simulée), rayon, plafond, validation IA."""

import pytest

from agency_scout import core


class FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.text = payload, status, str(payload)

    def json(self):
        return self._p


PLACES = {"places": [
    {"id": "near", "displayName": {"text": "Agence Proche"}, "formattedAddress": "10 rue X, 75020 Paris",
     "location": {"latitude": 48.8560, "longitude": 2.3990}, "websiteUri": "https://www.proche.fr/"},
    {"id": "far", "displayName": {"text": "Agence Loin"}, "formattedAddress": "Lyon",
     "location": {"latitude": 45.76, "longitude": 4.83}, "websiteUri": "https://loin.fr"},
    {"id": "nosite", "displayName": {"text": "Sans Site"}, "formattedAddress": "75020 Paris",
     "location": {"latitude": 48.8554, "longitude": 2.3985}},
]}


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(core.requests.Session, "post", lambda self, *a, **k: FakeResp(PLACES))
    conn = core.connect(tmp_path / "t.db")
    yield conn
    conn.close()


def test_discover_keeps_only_places_inside_radius(db):
    ids = core.discover(db, ["agence web"], (48.85536, 2.39845), 3000, "key")
    assert set(ids) == {"near", "nosite"}
    row = db.execute("SELECT * FROM agencies WHERE place_id='near'").fetchone()
    assert row["domain"] == "proche.fr" and row["distance_m"] < 100


def test_monthly_cap_is_a_hard_stop(db, monkeypatch):
    monkeypatch.setattr(core, "MONTHLY_CAP", 1)
    core.search_places(db, "q", (48.85, 2.39), 1000, "key")
    with pytest.raises(core.QuotaReached):
        core.search_places(db, "q", (48.85, 2.39), 1000, "key")


def test_invalid_llm_output_is_stored_as_error(monkeypatch):
    monkeypatch.setattr(core, "fetch_site_text", lambda url: ("Nous créons des sites web pour nos clients. " * 5, [url]))
    monkeypatch.setattr(core, "llm_complete", lambda s, u: ({"categorie": "boulangerie", "score": 42}, "fake"))
    result = core.analyze("x.fr", "https://x.fr", None, "sys")
    assert result["error"].startswith("analyse IA invalide")


def test_invented_proof_is_flagged(monkeypatch):
    monkeypatch.setattr(core, "fetch_site_text", lambda url: ("Nous créons des sites web pour nos clients. " * 5, [url]))
    monkeypatch.setattr(core, "llm_complete", lambda s, u: (
        {"categorie": "agence", "score": 7, "resume": "ok", "preuve": "Leader européen du WordPress headless"}, "fake"))
    assert core.analyze("x.fr", "https://x.fr", None, "sys")["preuve_ok"] == 0
