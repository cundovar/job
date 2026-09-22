#!/usr/bin/env python3
"""Client de l'API publique Recherche d'Entreprises (annuaire-entreprises.data.gouv.fr).

Ce module ne sait qu'une chose : lister des **candidats**. Le registre agrège
Sirene et le RNE ; il dit qui est immatriculé, où est le siège et quel code APE
a été déclaré. Il ne dit pas ce que la structure fait vraiment, et il ne dit
jamais à quel site web elle appartient — il n'en publie aucun.

C'est pour cela que chaque résultat sort marqué `status: 'candidate'` :

- un 62.01Z (programmation informatique) couvre indifféremment une agence web,
  une ESN, un freelance en régie ou une activité sans rapport ;
- une adresse légale prouve un siège, pas un lieu de travail ni une activité ;
- un nom proche d'un nom de domaine ne prouve pas que le domaine est le sien.

L'activité réelle est confirmée ailleurs, par l'auto-description du site lue par
le Vérificateur. Traiter ce module comme un oracle d'activité rouvrirait
exactement la porte que le projet a fermée : publier une agence que personne
n'a vérifiée.

Aucun secret, aucun jeton : l'API est ouverte. Le réseau est injectable
(`opener=`) pour que la suite de tests tourne hors ligne.
"""
from __future__ import annotations

import json
import re
import signal
import time
import urllib.parse
from typing import Any, Callable, Dict, Iterable, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SEARCH_URL = "https://recherche-entreprises.api.gouv.fr/search"
USER_AGENT = "job-search-automation/1.0 (prospection agences; +https://varascundo.com)"

# La documentation annonce 7 appels/s. On se tient volontairement en dessous :
# dépasser ferait tomber le registre entier, alors que ralentir ne coûte qu'un
# run un peu plus long.
MAX_CALLS_PER_SECOND = 5
DEFAULT_TIMEOUT_SECONDS = 12
DEFAULT_PER_PAGE = 25
DEFAULT_MAX_PAGES = 4

# Codes APE qui rendent une structure *candidate* à la voie « agence web ».
# Aucun de ces codes ne prouve qu'il s'agit d'une agence.
NAF_AGENCE = (
    "62.01Z",  # Programmation informatique
    "62.02A",  # Conseil en systèmes et logiciels informatiques
    "62.09Z",  # Autres activités informatiques
    "63.11Z",  # Traitement de données, hébergement
    "63.12Z",  # Portails internet
    "73.11Z",  # Agences de publicité
    "74.10Z",  # Activités spécialisées de design
)

# Codes APE qui rendent une structure candidate à la voie « formation ».
NAF_FORMATION = (
    "85.59A",  # Formation continue d'adultes
    "85.59B",  # Autres enseignements
    "85.32Z",  # Enseignement secondaire technique ou professionnel
    "85.42Z",  # Enseignement supérieur
    "85.60Z",  # Activités de soutien à l'enseignement
)

ACTIVE_STATE = "A"

# Le registre masque les structures non diffusibles au lieu de les omettre.
# Le nom devient un gabarit et l'adresse disparaît : c'est un résultat réel dont
# l'adresse est inconnue, surtout pas une adresse à reconstituer.
NON_DIFFUSIBLE_MARKERS = ("information non-diffusible", "information non diffusible")

LEGAL_ADDRESS_SOURCE = "registre (Sirene/RNE via API Recherche d'Entreprises)"
REGISTRY_SOURCE = "registre:recherche-entreprises"


class RegistryError(RuntimeError):
    """Le registre n'a pas répondu de façon exploitable.

    Levée, jamais avalée : un appelant qui reçoit une liste vide la relit comme
    « il n'y a aucune entreprise ici », ce qui est faux et pousse à combler le
    vide. Une panne doit se voir.
    """


def _default_opener(url: str, timeout: int) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    # `urlopen(timeout=)` ne borne que la socket une fois connectée : la
    # résolution DNS et l'établissement TCP qui la précèdent gardent leurs
    # propres délais, bien plus longs. Un registre injoignable fige alors le
    # run entier sans lever d'exception. L'alarme dure borne tout le chemin.
    def _alarm(_signum, _frame):
        raise TimeoutError(f"registre : délai dépassé ({timeout}s) sur {url}")

    previous = signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_non_diffusible(name: str) -> bool:
    lowered = name.casefold()
    return any(marker in lowered for marker in NON_DIFFUSIBLE_MARKERS)


def normalize_result(raw: Dict[str, Any]) -> Dict[str, Any] | None:
    """Transforme un résultat brut de l'API en candidat du pipeline.

    Renvoie `None` quand le résultat n'a pas de SIREN : sans identifiant, il
    n'est ni dédoublonnable ni vérifiable, et l'ajouter reviendrait à publier
    une ligne que personne ne peut retrouver.
    """
    siren = _text(raw.get("siren"))
    if not siren:
        return None

    siege = raw.get("siege") if isinstance(raw.get("siege"), dict) else {}
    name = _text(raw.get("nom_complet")) or _text(raw.get("nom_raison_sociale"))
    state = _text(siege.get("etat_administratif")) or _text(raw.get("etat_administratif"))

    # `geo_adresse` est l'adresse rapprochée de la BAN, `adresse` la forme brute
    # Sirene. L'une comme l'autre est une adresse *lue dans le registre* ; on ne
    # la recompose jamais à partir des champs voie/commune, ce qui reviendrait à
    # fabriquer une adresse à partir d'un code postal.
    legal_address = _text(siege.get("geo_adresse")) or _text(siege.get("adresse"))
    postal_code = _text(siege.get("code_postal"))
    if not legal_address:
        postal_code = ""

    activity_code = _text(siege.get("activite_principale")) or _text(raw.get("activite_principale"))

    return {
        "name": name,
        "siren": siren,
        "siret": _text(siege.get("siret")) or None,
        "website": None,  # le registre n'en publie pas : ne rien deviner ici
        "activity_code": activity_code,
        "activity_label": _text(raw.get("libelle_activite_principale")),
        "legal_form": _text(raw.get("nature_juridique")),
        "administrative_state": state,
        "is_active": state == ACTIVE_STATE,
        "diffusible": not _is_non_diffusible(name),
        "legal_address": legal_address or None,
        "legal_address_source": LEGAL_ADDRESS_SOURCE if legal_address else None,
        "postal_code": postal_code or None,
        "commune_label": _text(siege.get("libelle_commune")) or None,
        "latitude": _float(siege.get("latitude")),
        "longitude": _float(siege.get("longitude")),
        "creation_date": _text(raw.get("date_creation")) or None,
        "headcount_range": _text(raw.get("tranche_effectif_salarie")) or None,
        "sources": [REGISTRY_SOURCE],
        # Le verdict d'activité n'appartient pas au registre. Ces deux champs
        # existent pour que personne n'ait à le déduire d'un silence.
        "status": "candidate",
        "why_candidate": (
            f"code APE {activity_code} relevé au registre — l'activité réelle n'est pas prouvée"
            if activity_code
            else "présent au registre sur la zone — l'activité réelle n'est pas prouvée"
        ),
    }


class RegistryClient:
    """Interroge l'API ouverte avec une cadence, une pagination et des erreurs bornées."""

    def __init__(
        self,
        *,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        per_page: int = DEFAULT_PER_PAGE,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_calls_per_second: float = MAX_CALLS_PER_SECOND,
        opener: Callable[[str, int], str] = _default_opener,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.timeout = timeout
        self.per_page = per_page
        self.max_pages = max_pages
        self.min_interval = 1.0 / max_calls_per_second if max_calls_per_second > 0 else 0.0
        self._opener = opener
        self._sleep = sleeper
        self._clock = clock
        self._last_call: float | None = None
        self.calls = 0

    def _throttle(self) -> None:
        if self._last_call is not None and self.min_interval:
            waited = self._clock() - self._last_call
            if waited < self.min_interval:
                self._sleep(self.min_interval - waited)
        self._last_call = self._clock()

    def _get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "", [])})
        url = f"{SEARCH_URL}?{query}"
        self._throttle()
        self.calls += 1
        try:
            body = self._opener(url, self.timeout)
        except HTTPError as exc:
            if exc.code == 429:
                raise RegistryError("registre : quota de requêtes dépassé (HTTP 429)") from exc
            raise RegistryError(f"registre : HTTP {exc.code} sur {url}") from exc
        except URLError as exc:
            raise RegistryError(f"registre injoignable : {exc.reason}") from exc
        except TimeoutError as exc:
            raise RegistryError(f"registre : délai dépassé après {self.timeout}s") from exc

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RegistryError("registre : réponse illisible (JSON invalide)") from exc
        if not isinstance(payload, dict):
            raise RegistryError("registre : réponse inattendue (objet JSON attendu)")
        return payload

    def search(
        self,
        *,
        query: str = "",
        code_postal: str = "",
        commune: str = "",
        departement: str = "",
        naf_codes: Iterable[str] = (),
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """Liste les candidats d'une zone, pagination et cadence comprises."""
        params = {
            "q": query,
            "code_postal": code_postal,
            "code_commune": commune,
            "departement": departement,
            "activite_principale": ",".join(naf_codes) if naf_codes else "",
            "per_page": self.per_page,
            "page": 1,
        }
        candidates: List[Dict[str, Any]] = []
        seen: set[str] = set()
        page = 1
        while page <= self.max_pages:
            params["page"] = page
            payload = self._get(params)
            results = payload.get("results")
            if not isinstance(results, list) or not results:
                break
            for raw in results:
                if not isinstance(raw, dict):
                    continue
                candidate = normalize_result(raw)
                if candidate is None:
                    continue
                if active_only and not candidate["is_active"]:
                    continue
                key = candidate["siret"] or candidate["siren"]
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(candidate)
            total_pages = payload.get("total_pages")
            if not isinstance(total_pages, int) or page >= total_pages:
                break
            page += 1
        return candidates


def search_zone_candidates(
    *,
    postal_codes: Iterable[str] = (),
    query: str = "",
    naf_codes: Iterable[str] = (),
    client: RegistryClient | None = None,
) -> List[Dict[str, Any]]:
    """Agrège les candidats de plusieurs codes postaux, dédoublonnés par SIRET/SIREN."""
    registry = client or RegistryClient()
    naf = tuple(naf_codes) or NAF_AGENCE + NAF_FORMATION
    merged: Dict[str, Dict[str, Any]] = {}
    for code in postal_codes or ("",):
        for candidate in registry.search(query=query, code_postal=code, naf_codes=naf):
            merged.setdefault(candidate["siret"] or candidate["siren"], candidate)
    return list(merged.values())


POSTAL_CODE_PATTERN = re.compile(r"^\d{5}$")


def postal_codes_of(terms: Iterable[str]) -> List[str]:
    """Extrait les codes postaux exacts d'une liste de termes de zone.

    Volontairement strict : « paris 20 » ou « belleville » ne sont pas des codes
    postaux, et en dériver un reviendrait à inventer une localisation.
    """
    return [term for term in terms if POSTAL_CODE_PATTERN.match(str(term).strip())]
