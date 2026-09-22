#!/usr/bin/env python3
"""Résolution d'un libellé de ville en périmètre géographique vérifiable.

Le prospecteur a longtemps travaillé sur un catalogue de zones écrit à la main
(`ZONES`). Chaque nouvelle ville demandait une modification du code source, et
la liste finissait par se lire comme « les villes supportées » alors qu'elle ne
disait que « les quatre périmètres que quelqu'un a eu le temps d'écrire ».

Ce module supprime ce catalogue de la chaîne : « Montreuil » devient une
commune réelle — nom officiel, code INSEE, codes postaux, département,
coordonnées du centre — obtenue de l'API Découpage administratif
(geo.api.gouv.fr), ouverte et sans jeton.

Trois refus assumés, tous pour la même raison qu'ailleurs dans ce projet — un
résultat vide ou approximatif se relit comme une vérité :

- une ville inconnue lève une erreur **en nommant des communes approchantes**,
  et ne déclenche aucune recherche de repli sur un périmètre voisin ;
- un homonyme (Montreuil existe en 93, en 85 et en 28) lève une erreur **en
  nommant les départements candidats** au lieu de choisir le plus peuplé ;
- la présence du nom de la ville dans une page web ne prouve rien. Le périmètre
  se juge sur le code postal d'une adresse réellement lue ou sur le code commune
  du registre (`locate_in_city`) ; une mention en page reste un indice nommé
  comme tel.

Le réseau est injectable (`opener=`) pour que la suite de tests tourne hors
ligne, comme dans `tools/agency_registry.py`.
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
from typing import Any, Callable, Dict, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

COMMUNES_URL = "https://geo.api.gouv.fr/communes"
DEPARTEMENTS_URL = "https://geo.api.gouv.fr/departements"
USER_AGENT = "job-search-automation/1.0 (prospection agences; +https://varascundo.com)"
SOURCE_LABEL = "geo.api.gouv.fr (API Découpage administratif)"

DEFAULT_TIMEOUT_SECONDS = 12
# Assez pour montrer les homonymes réels sans transformer l'erreur en annuaire.
DEFAULT_LIMIT = 15

COMMUNE_FIELDS = "nom,code,codesPostaux,codeDepartement,codeRegion,centre,population"


class CityResolutionError(RuntimeError):
    """La ville demandée n'a pas donné un périmètre unique et vérifiable.

    Levée au lieu de renvoyer un périmètre par défaut : chercher ailleurs que là
    où l'utilisateur a demandé, sans le dire, produirait une passe qui *paraît*
    ciblée et ne l'est pas.
    """


class AmbiguousCityError(CityResolutionError):
    """Plusieurs communes portent ce nom : le département doit être fourni."""

    def __init__(self, message: str, candidates: List[Dict[str, Any]]) -> None:
        super().__init__(message)
        self.candidates = candidates


def _default_opener(url: str, timeout: int) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def normalize_name(value: str) -> str:
    """Forme comparable d'un nom de commune : sans accent, sans ponctuation.

    « Saint-Étienne », « saint etienne » et « SAINT ETIENNE » désignent la même
    commune ; « Montreuil-Juigné » n'est pas « Montreuil » et ne doit jamais
    être rapproché d'elle par une comparaison en sous-chaîne.
    """
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = text.casefold().replace("'", " ").replace("’", " ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def slugify(value: str) -> str:
    return normalize_name(value).replace(" ", "-")


def normalize_departement(value: Any) -> str:
    """Code département tel que l'API le publie : « 93 », « 05 », « 2A », « 974 »."""
    raw = str(value or "").strip().upper()
    if not raw:
        return ""
    if raw in ("2A", "2B"):
        return raw
    if raw.isdigit():
        # « 5 » saisi à la main est le 05 ; « 974 » reste sur trois chiffres.
        return raw.zfill(2) if len(raw) < 2 else raw
    return raw


def _fetch_json(url: str, opener: Callable[[str, int], str], timeout: int) -> Any:
    try:
        body = opener(url, timeout)
    except HTTPError as exc:
        raise CityResolutionError(
            f"résolution de commune : HTTP {exc.code} sur {COMMUNES_URL}"
        ) from exc
    except URLError as exc:
        raise CityResolutionError(
            f"résolution de commune : {SOURCE_LABEL} injoignable ({exc.reason})"
        ) from exc
    except TimeoutError as exc:
        raise CityResolutionError(
            f"résolution de commune : délai dépassé après {timeout}s"
        ) from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise CityResolutionError(
            "résolution de commune : réponse illisible (JSON invalide)"
        ) from exc


def _commune_from_raw(raw: Dict[str, Any], departement_name: str = "") -> Dict[str, Any]:
    centre = raw.get("centre") if isinstance(raw.get("centre"), dict) else {}
    coordinates = centre.get("coordinates") if isinstance(centre.get("coordinates"), list) else []
    # GeoJSON publie [longitude, latitude] — l'inverser placerait Montreuil au
    # large de la Somalie, et personne ne le verrait avant la première distance.
    longitude = coordinates[0] if len(coordinates) == 2 else None
    latitude = coordinates[1] if len(coordinates) == 2 else None

    name = str(raw.get("nom") or "").strip()
    departement = normalize_departement(raw.get("codeDepartement"))
    postal_codes = [
        str(code).strip()
        for code in (raw.get("codesPostaux") or [])
        if str(code).strip()
    ]
    return {
        "name": name,
        "slug": slugify(name),
        "insee": str(raw.get("code") or "").strip(),
        "departement": departement,
        "departement_name": departement_name,
        "postal_codes": sorted(set(postal_codes)),
        "latitude": latitude,
        "longitude": longitude,
        "population": raw.get("population"),
        "label": f"{name} ({departement})" if departement else name,
        "source": SOURCE_LABEL,
    }


def _departement_name(
    code: str, opener: Callable[[str, int], str], timeout: int
) -> str:
    """Nom du département, utile aux requêtes et à l'affichage — jamais bloquant.

    Son absence dégrade l'étiquette, pas le périmètre : le code INSEE et les
    codes postaux suffisent à décider qui est dans la commune.
    """
    if not code:
        return ""
    try:
        payload = _fetch_json(f"{DEPARTEMENTS_URL}/{code}", opener, timeout)
    except CityResolutionError:
        return ""
    if isinstance(payload, dict):
        return str(payload.get("nom") or "").strip()
    return ""


def resolve_city(
    name: str,
    departement: str | None = None,
    *,
    opener: Callable[[str, int], str] = _default_opener,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    limit: int = DEFAULT_LIMIT,
) -> Dict[str, Any]:
    """Transforme « Montreuil » en commune unique, ou explique pourquoi c'est impossible."""
    query = str(name or "").strip()
    if not query:
        raise CityResolutionError(
            "Aucune ville demandée : passe --ville \"Montreuil\" (et --departement 93 "
            "si le nom est porté par plusieurs communes)."
        )

    params = {
        "nom": query,
        "fields": COMMUNE_FIELDS,
        "boost": "population",
        "limit": limit,
    }
    wanted_departement = normalize_departement(departement)
    if wanted_departement:
        params["codeDepartement"] = wanted_departement

    url = f"{COMMUNES_URL}?{urllib.parse.urlencode(params)}"
    payload = _fetch_json(url, opener, timeout)
    if not isinstance(payload, list):
        raise CityResolutionError(
            "résolution de commune : réponse inattendue (liste JSON attendue)"
        )

    communes = [_commune_from_raw(raw) for raw in payload if isinstance(raw, dict)]
    target = normalize_name(query)
    # La recherche de l'API est approximative : « Montreuil » ramène aussi
    # « Montreuil-Juigné ». Seule l'égalité du nom normalisé fait une commune
    # demandée ; le reste ne sert qu'à nommer les approchants dans l'erreur.
    exact = [commune for commune in communes if normalize_name(commune["name"]) == target]

    if not exact:
        near = ", ".join(f"{c['label']}" for c in communes[:8])
        if wanted_departement:
            raise CityResolutionError(
                f"Ville inconnue : « {query} » n'existe pas dans le département "
                f"{wanted_departement} d'après {SOURCE_LABEL}."
                + (f" Communes approchantes : {near}." if near else "")
                + " Aucune recherche de repli n'a été lancée : corrige le nom ou le département."
            )
        raise CityResolutionError(
            f"Ville inconnue : aucune commune ne s'appelle « {query} » d'après {SOURCE_LABEL}."
            + (f" Communes approchantes : {near}." if near else "")
            + " Exemples valides : Montreuil (93), Lille (59), Nantes (44)."
            + " Aucune recherche de repli n'a été lancée."
        )

    if len(exact) > 1:
        detail = " · ".join(
            f"{c['name']} ({c['departement']}"
            + (f", {', '.join(c['postal_codes'])}" if c["postal_codes"] else "")
            + ")"
            for c in exact
        )
        raise AmbiguousCityError(
            f"Ville ambiguë : {len(exact)} communes s'appellent « {query} » — {detail}. "
            "Précise le département, ex. --departement "
            f"{exact[0]['departement']}.",
            exact,
        )

    commune = exact[0]
    if not commune["insee"] or not commune["postal_codes"]:
        raise CityResolutionError(
            f"Commune « {commune['label']} » incomplète dans {SOURCE_LABEL} "
            "(code INSEE ou code postal absent) : périmètre non vérifiable."
        )
    commune["departement_name"] = _departement_name(commune["departement"], opener, timeout)
    if commune["departement_name"]:
        commune["label"] = f"{commune['name']} ({commune['departement']} · {commune['departement_name']})"
    return commune


# ── Périmètre : ce qui fait qu'un candidat appartient à la ville ─────────────

# Le nom seul ne prouve rien : « nous intervenons à Montreuil » se lit dans une
# page d'une agence lyonnaise. Les deux premiers niveaux valent preuve, le
# troisième reste un indice nommé.
PERIMETER_ADDRESS = 'adresse'
PERIMETER_REGISTRY = 'registre'
PERIMETER_MENTION = 'mention'
PERIMETER_NONE = 'aucun'

PERIMETER_RANK = {
    PERIMETER_ADDRESS: 0,
    PERIMETER_REGISTRY: 1,
    PERIMETER_MENTION: 2,
    PERIMETER_NONE: 3,
}
PERIMETER_VERIFIED = (PERIMETER_ADDRESS, PERIMETER_REGISTRY)

# Vocabulaire de `address_how` du prospecteur : seules ces deux provenances
# viennent d'une adresse réellement lue. Dupliqué ici volontairement pour que ce
# module reste importable seul, et vérifié par les tests des deux côtés.
ADDRESS_HOW_READ = ('adresse', 'contact/legales')
REGISTRY_HOW = 'siège (registre)'


def locate_in_city(agency: Dict[str, Any], commune: Dict[str, Any]) -> tuple[str, str]:
    """Dit à quel titre un candidat appartient à la commune, et sur quelle preuve.

    Renvoie `(niveau, preuve)`. L'ordre des tests est l'ordre de la confiance :
    une adresse lue, puis un siège au registre, puis — faute de mieux — une
    mention en page, qui ne fait jamais entrer personne dans le périmètre
    vérifié.
    """
    postal_codes = set(commune.get("postal_codes") or ())
    insee = str(commune.get("insee") or "")
    how = str(agency.get("how") or "")
    postal = str(agency.get("postal_code") or "").strip()

    if postal and postal in postal_codes and how in ADDRESS_HOW_READ:
        return PERIMETER_ADDRESS, f"code postal {postal} lu dans une adresse ({how})"

    commune_code = str(agency.get("commune_code") or "")
    if insee and commune_code == insee:
        return PERIMETER_REGISTRY, f"code commune {insee} au registre"
    if postal and postal in postal_codes and how == REGISTRY_HOW:
        return PERIMETER_REGISTRY, f"siège en {postal} au registre"

    if agency.get("zone_match") in ("tier1", "tier2"):
        return PERIMETER_MENTION, f"mention « {agency.get('zone_term') or commune.get('name')} » en page"
    return PERIMETER_NONE, ""


def in_perimeter(agency: Dict[str, Any], commune: Dict[str, Any]) -> bool:
    """Vrai seulement sur preuve d'adresse ou de registre — jamais sur une mention."""
    return locate_in_city(agency, commune)[0] in PERIMETER_VERIFIED


# ── Périmètre de recherche dérivé de la commune ──────────────────────────────


def city_zone_key(commune: Dict[str, Any]) -> str:
    """Clé de zone d'une ville : `ville-<slug>-<departement>`.

    Le département fait partie de la clé parce que deux Montreuil existent : sans
    lui, deux recherches différentes partageraient un identifiant et l'historique
    mélangerait leurs résultats.
    """
    return f"ville-{commune['slug']}-{commune['departement']}".strip("-")


def city_zone(commune: Dict[str, Any]) -> Dict[str, Any]:
    """Périmètre au format attendu par le prospecteur, construit à la volée.

    `tier1` porte ce qui désigne la commune elle-même, `tier2` son département :
    ces termes servent au tri et aux indices, jamais à décider qu'une adresse
    est dans la ville — c'est le rôle de `locate_in_city`.
    """
    tier1 = list(commune["postal_codes"])
    for variant in (commune["name"], commune["slug"], commune["slug"].replace("-", " ")):
        variant = str(variant).strip()
        if variant and variant.lower() not in [t.lower() for t in tier1]:
            tier1.append(variant)

    tier2 = [commune["departement"]] if commune["departement"] else []
    if commune.get("departement_name"):
        tier2.append(commune["departement_name"])
        tier2.append(slugify(commune["departement_name"]))

    return {
        "label": commune["label"],
        "tier1": tier1,
        "tier2": tier2,
        "city": commune["name"],
        "insee": commune["insee"],
        "postal_codes": list(commune["postal_codes"]),
        "departement": commune["departement"],
        "centre": {"latitude": commune["latitude"], "longitude": commune["longitude"]},
        "source": commune["source"],
    }


# Deux familles, conservées de la requête jusqu'au résultat. La seconde existe
# parce qu'un organisme de formation n'est pas une agence ratée : c'est une
# cible différente, avec son propre vocabulaire, et la fondre dans la première
# revenait à ne jamais en trouver.
FAMILY_AGENCY = 'agence'
FAMILY_FORMATION = 'formation'

AGENCY_QUERY_TEMPLATES = (
    "agence web {city} WordPress",
    "agence digitale {city} création site internet",
    "studio développement web {city}",
    "développeur web freelance agence {city} {postal}",
)
FORMATION_QUERY_TEMPLATES = (
    "organisme de formation numérique {city}",
    "formation développeur web {city}",
    "formation accessibilité RGAA {city} {departement}",
)


def query_families(commune: Dict[str, Any]) -> Dict[str, List[str]]:
    """Les deux familles de requêtes de la ville, étiquetées par famille."""
    context = {
        "city": commune["name"],
        "postal": (commune["postal_codes"] or [""])[0],
        "departement": commune.get("departement_name") or commune["departement"],
    }
    return {
        FAMILY_AGENCY: [t.format(**context).strip() for t in AGENCY_QUERY_TEMPLATES],
        FAMILY_FORMATION: [t.format(**context).strip() for t in FORMATION_QUERY_TEMPLATES],
    }


def city_queries(commune: Dict[str, Any]) -> List[str]:
    """Les requêtes des deux familles, à plat, dans l'ordre de publication."""
    families = query_families(commune)
    return families[FAMILY_AGENCY] + families[FAMILY_FORMATION]
