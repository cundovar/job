"""duplicate_check : cette organisation est-elle déjà connue, contactée ou exclue ?

Le domaine normalisé est la seule clé fiable. Le nom d'entreprise ne l'est pas :
comparé en sous-chaîne, il rapproche « Jaam » de « Jaamix » (un envoi bloqué
sans raison) et sépare « Jaam » de « Jaam SARL » (un deuxième envoi à la même
structure). Le domaine tranche le second cas ; pour le premier on ne garde que
l'égalité stricte des noms, jamais l'inclusion.

Le nom reste nécessaire malgré tout : une candidature partie via une annonce
porte l'URL de l'annonce, pas celle de l'entreprise. Les deux clés sont donc
complémentaires, et il suffit qu'une seule corresponde.

Même contrat de sortie que les collecteurs : {tool, url, value, evidence,
measured_at, error}.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from .collectors import _measurement, normalize_domain

# Formes juridiques et habillages qui n'identifient pas l'organisation.
# Volontairement court : chaque entrée retirée est une distinction perdue.
LEGAL_FORMS = ("sarl", "sarlu", "sas", "sasu", "sa", "eurl", "scop", "scic", "sci", "asso")

EXCLUDED_STATUS = "ecartee"


def domain_of(url: str) -> str:
    """Domaine normalisé, ou chaîne vide si l'URL n'en livre aucun.

    urlparse accepte n'importe quelle chaîne comme hôte : « pas une url » en
    ressort tel quel. Ici un domaine invalide doit valoir « je ne sais pas »,
    pour que la comparaison retombe sur le nom au lieu de croire à une clé.
    """
    measured = normalize_domain(url)
    if measured["error"]:
        return ""
    domain = measured["value"]["domain"]
    return domain if "." in domain and " " not in domain else ""


def normalize_name(name: str) -> str:
    """Nom comparable : casse, ponctuation et forme juridique neutralisées."""
    flattened = re.sub(r"[^\w\s]", " ", str(name or ""), flags=re.UNICODE).casefold()
    words = [word for word in flattened.split() if word not in LEGAL_FORMS]
    return " ".join(words)


def same_organisation(url_a: str, name_a: str, url_b: str, name_b: str) -> str:
    """Motif du rapprochement, ou chaîne vide si ce sont deux organisations."""
    domain_a = domain_of(url_a)
    if domain_a and domain_a == domain_of(url_b):
        return f"même domaine {domain_a}"
    normalized = normalize_name(name_a)
    if normalized and normalized == normalize_name(name_b):
        return f"même nom « {str(name_b).strip()} »"
    return ""


def _matches(
    url: str, name: str, entries: Iterable[Dict[str, Any]], url_field: str, name_field: str
) -> List[Dict[str, str]]:
    found = []
    for entry in entries:
        reason = same_organisation(url, name, entry.get(url_field, ""), entry.get(name_field, ""))
        if reason:
            found.append({"label": str(entry.get(name_field) or entry.get(url_field) or ""), "reason": reason})
    return found


def duplicate_check(
    url: str,
    name: str = "",
    *,
    contacted: Iterable[Dict[str, Any]] = (),
    registry: Iterable[Dict[str, Any]] = (),
) -> Dict[str, Any]:
    """Confronte une cible aux deux registres locaux.

    `contacted` : les envois déjà partis (champs `company` et `url`).
    `registry`  : les entreprises listées (champs `nom`, `site`, `statut`) ;
                  `statut: ecartee` vaut interdiction de contact.
    """
    registry = list(registry)
    excluded_rows = [row for row in registry if str(row.get("statut") or "") == EXCLUDED_STATUS]

    hits = {
        "contacted": _matches(url, name, contacted, "url", "company"),
        "excluded": _matches(url, name, excluded_rows, "site", "nom"),
        "known": _matches(url, name, registry, "site", "nom"),
    }
    domain = domain_of(url)
    evidence = "; ".join(
        f"{kind} : {found[0]['reason']}" for kind, found in hits.items() if found
    ) or f"aucun doublon pour {domain or name or url or 'cible sans identifiant'}"

    return _measurement(
        "duplicate_check",
        url,
        value={"domain": domain, **hits},
        evidence=evidence,
    )
