"""Client Google Places Text Search (New) — point d'accès HTTP unique.

Deux niveaux :
- ``places_text_search`` : appel brut (construction de la requête, exécution,
  pagination). Le rappel ``on_request`` est invoqué avant chaque appel facturé
  et peut lever une exception pour imposer un plafond (agency_scout).
- ``search_places`` / ``discover_paris_20`` : normalisation pour le pipeline
  V2 (``tools/agency_prospecting_v2.py``), qui ne retient que les lieux avec
  un site.

Le module ne lance aucun appel à l'import et ne journalise jamais la clé.
"""
from __future__ import annotations

import json
from typing import Callable
from urllib.request import Request, urlopen


ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
# ``places.location`` et ``nextPageToken`` servent au scout (distance + pagination) ;
# la V2 les reçoit et les ignore. Demander websiteUri place l'appel au palier
# « Text Search Enterprise » — c'est déjà le cas des deux consommateurs.
FIELD_MASK = ",".join((
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.addressComponents",
    "places.location",
    "places.websiteUri",
    "places.googleMapsUri",
    "places.businessStatus",
    "places.types",
    "nextPageToken",
))


def _build_request(body: dict, api_key: str) -> Request:
    return Request(
        ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
    )


def places_text_search(
    query: str,
    api_key: str,
    opener: Callable = urlopen,
    timeout: int = 15,
    location_bias: tuple[float, float, int] | None = None,
    page_size: int | None = None,
    max_pages: int = 1,
    on_request: Callable[[], None] | None = None,
) -> list[dict]:
    """Retourne les ``places`` brutes de Google pour une requête.

    ``location_bias`` est ``(lat, lng, rayon_m)`` : Google le traite comme une
    préférence, jamais comme un filtre — le filtrage reste à l'appelant.
    ``on_request`` est invoqué avant chaque appel HTTP facturé (pages de
    pagination comprises) ; une exception qu'il lève interrompt la collecte.
    """
    if not api_key:
        return []
    body: dict = {
        "textQuery": query,
        "languageCode": "fr",
        "regionCode": "FR",
    }
    if page_size:
        body["pageSize"] = page_size
    if location_bias:
        lat, lng, radius_m = location_bias
        body["locationBias"] = {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": float(min(radius_m, 50_000)),
            }
        }
    places: list[dict] = []
    for _ in range(max(1, max_pages)):
        if on_request:
            on_request()
        request = _build_request(body, api_key)
        with opener(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        places.extend(payload.get("places") or [])
        token = payload.get("nextPageToken")
        if not token:
            break
        body["pageToken"] = token
    return places


def _postal_code(place: dict) -> str | None:
    for component in place.get("addressComponents") or []:
        if "postal_code" in (component.get("types") or []):
            return component.get("longText") or component.get("shortText")
    return None


def search_places(
    query: str,
    api_key: str,
    opener: Callable = urlopen,
    timeout: int = 15,
) -> list[dict]:
    """Normalisation V2 : seuls les lieux avec un site deviennent des pistes."""
    rows = []
    for place in places_text_search(query, api_key, opener=opener, timeout=timeout):
        website = str(place.get("websiteUri") or "").strip()
        if not website:
            continue
        rows.append({
            "place_id": place.get("id"),
            "name": (place.get("displayName") or {}).get("text") or website,
            "website": website,
            "address": place.get("formattedAddress") or None,
            "postal_code": _postal_code(place),
            "google_maps_url": place.get("googleMapsUri") or None,
            "business_status": place.get("businessStatus") or None,
            "types": place.get("types") or [],
            "source": "google_places",
        })
    return rows


def discover_paris_20(api_key: str, opener: Callable = urlopen) -> list[dict]:
    """Deux recherches bornées : agences puis formations du 20e."""
    rows = []
    seen = set()
    for query in (
        "agence web Paris 20 75020",
        "organisme formation numérique Paris 20 75020",
    ):
        for place in search_places(query, api_key, opener=opener):
            identity = place.get("place_id") or place["website"]
            if identity in seen:
                continue
            seen.add(identity)
            rows.append(place)
    return rows
