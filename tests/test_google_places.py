import json
from urllib.parse import urlparse

from tools.google_places import ENDPOINT, discover_paris_20, search_places


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_text_search_normalizes_only_useful_fields():
    captured = {}

    def opener(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse({"places": [{
            "id": "place-1",
            "displayName": {"text": "Studio Test"},
            "formattedAddress": "1 rue Test, 75020 Paris, France",
            "addressComponents": [{"longText": "75020", "types": ["postal_code"]}],
            "websiteUri": "https://studio.test/",
            "googleMapsUri": "https://maps.google.com/?cid=1",
            "businessStatus": "OPERATIONAL",
            "types": ["consultant"],
        }]})

    rows = search_places("agence web Paris 20", "key-for-test", opener=opener)

    assert urlparse(captured["request"].full_url).geturl() == ENDPOINT
    assert captured["request"].get_header("X-goog-api-key") == "key-for-test"
    assert rows == [{
        "place_id": "place-1",
        "name": "Studio Test",
        "website": "https://studio.test/",
        "address": "1 rue Test, 75020 Paris, France",
        "postal_code": "75020",
        "google_maps_url": "https://maps.google.com/?cid=1",
        "business_status": "OPERATIONAL",
        "types": ["consultant"],
        "source": "google_places",
    }]


def test_missing_key_makes_no_external_call():
    called = False

    def opener(*_args, **_kwargs):
        nonlocal called
        called = True

    assert search_places("agence web Paris 20", "", opener=opener) == []
    assert called is False


def test_paris_20_deduplicates_places_across_two_queries():
    calls = 0

    def opener(_request, timeout):
        nonlocal calls
        calls += 1
        return FakeResponse({"places": [{
            "id": "same-place",
            "displayName": {"text": "Agence Formation"},
            "formattedAddress": "75020 Paris",
            "addressComponents": [{"longText": "75020", "types": ["postal_code"]}],
            "websiteUri": "https://same.test/",
        }]})

    assert len(discover_paris_20("key-for-test", opener=opener)) == 1
    assert calls == 2
