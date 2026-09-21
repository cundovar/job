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
