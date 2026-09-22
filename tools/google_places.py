"""Collecteur local minimal via Google Places Text Search (New).

Il ne s'active que si ``GOOGLE_PLACES_API_KEY`` est fourni par l'environnement.
Le module ne lance aucun appel à l'import et ne journalise jamais la clé.
"""
from __future__ import annotations

import json
from typing import Callable
from urllib.request import Request, urlopen


ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join((
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.addressComponents",
    "places.websiteUri",
    "places.googleMapsUri",
    "places.businessStatus",
    "places.types",
))


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
    """Retourne uniquement les champs nécessaires au pipeline d'agences."""
    if not api_key:
        return []
    body = json.dumps({
        "textQuery": query,
        "languageCode": "fr",
        "regionCode": "FR",
    }).encode("utf-8")
    request = Request(ENDPOINT, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    })
    with opener(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    rows = []
    for place in payload.get("places") or []:
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
