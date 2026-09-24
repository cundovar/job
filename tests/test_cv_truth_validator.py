"""Le validateur contrôle sans jamais réécrire.

Toutes les données viennent de fixtures synthétiques : cette suite doit tourner
sur un clone neuf, sans `data/`.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from cv_generator.cv_truth_validator import (
    parse_source_reference,
    sourced_experience_ids,
    validate_cv_content,
)

FIXTURE = Path(__file__).parent / "fixtures" / "careco_cv_case.json"


@pytest.fixture()
def careco():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture()
def master(careco):
    return careco["master"]


def _grouped_cv():
    """Le cas CARECO : un groupe qui conserve trois preuves de deux missions."""
    return {
        "base_variant": "webmaster",
        "cv": {
            "title": "Webmaster",
            "profile": "Webmaster de test, profil entierement invente.",
            "section_order": ["profile", "skills", "experiences", "projects", "education"],
            "skills": [
                {"title": "CMS", "items": ["WordPress", "WooCommerce"]},
                {"title": "Développement", "items": ["Twig", "Bootstrap", "Git"]},
            ],
            "experiences": [
                {
                    "id": "missions_techniques_2026",
                    "source_experience_ids": ["boutique_fictive", "atelier_imaginaire"],
                    "bullets": [
                        {
                            "text": "Catalogue WooCommerce et API REST sur une boutique inventée.",
                            "sources": ["boutique_fictive:0", "boutique_fictive:1"],
                        },
                        {
                            "text": "Gabarits Twig et Bootstrap maintenus sur un site inventé.",
                            "sources": ["atelier_imaginaire:0"],
                        },
                        {
                            "text": "Travail en branches Git sur une base de code fictive.",
                            "sources": ["atelier_imaginaire:1"],
                        },
                    ],
                },
                {
                    "id": "permanence_test",
                    "bullets": [
                        {
                            "text": "Accompagnement d'usagers fictifs sur des outils bureautiques.",
                            "sources": ["permanence_test:0"],
                        }
                    ],
                },
            ],
            "projects": [
                {
                    "id": "projet_vitrine",
                    "description": "Site inventé, utilisé uniquement pour les tests.",
                    "technologies": ["WordPress"],
                }
            ],
            "education": [{"title": "Titre professionnel Developpeur web (fictif)"}],
        },
    }


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


def test_valid_grouped_cv_passes_without_any_mutation(master):
    """Un contenu exact est accepté, et ressort rigoureusement identique."""
    content = _grouped_cv()
    before = copy.deepcopy(content)

    report = validate_cv_content(content, master)

    assert report["ok"], report["issues"]
    assert report["truth_issues"] == []
    assert report["content"] is content
    assert content == before


def test_group_keeps_every_member_evidence(master):
    """Le défaut CARECO : trois puces de deux missions survivent au groupement."""
    report = validate_cv_content(_grouped_cv(), master)
    assert report["truth_issues"] == []

    bullets = _grouped_cv()["cv"]["experiences"][0]["bullets"]
    assert len(bullets) == 3
    cited = {source.split(":")[0] for bullet in bullets for source in bullet["sources"]}
    assert cited == {"boutique_fictive", "atelier_imaginaire"}


def test_sourced_ids_expand_a_group_into_its_members(master):
    """Un bloc groupé prouve chacun de ses membres, pas seulement le groupe."""
    assert sourced_experience_ids(_grouped_cv()["cv"]) == [
        "boutique_fictive",
        "atelier_imaginaire",
        "permanence_test",
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("boutique_fictive:0", ("experience", "boutique_fictive", 0)),
        ("projet_vitrine", ("project", "projet_vitrine", None)),
        ("boutique_fictive:", None),
        (":0", None),
        ("", None),
    ],
)
def test_source_reference_grammar(raw, expected):
    assert parse_source_reference(raw) == expected


def test_legacy_highlight_indexes_remain_readable(master):
    """L'ancien champ reste lisible pendant la migration, sans rien réécrire."""
    content = _grouped_cv()
    content["cv"]["experiences"][1]["bullets"] = [
        {
            "text": "Accompagnement d'usagers fictifs sur des outils bureautiques.",
            "source_highlight_indexes": [0],
        }
    ]

    report = validate_cv_content(content, master)

    assert report["truth_issues"] == []


def test_assembled_cv_shape_is_validated_through_parallel_sources(master):
    """Le CV assemblé porte ses puces en texte et sa provenance à côté."""
    content = _grouped_cv()
    experience = content["cv"]["experiences"][1]
    experience["bullets"] = ["Accompagnement d'usagers fictifs sur des outils bureautiques."]
    experience["bullet_sources"] = [["permanence_test:0"]]

    report = validate_cv_content(content, master)

    assert report["truth_issues"] == []


# --------------------------------------------------------------------------- #
# Sources inconnues
# --------------------------------------------------------------------------- #


def test_unknown_experience_is_located_precisely(master):
    content = _grouped_cv()
    content["cv"]["experiences"][1]["id"] = "mission_fantome"
    content["cv"]["experiences"][1]["bullets"][0]["sources"] = ["mission_fantome:0"]

    report = validate_cv_content(content, master)

    codes = {item["code"]: item for item in report["truth_issues"]}
    assert "UNKNOWN_EXPERIENCE" in codes
    assert codes["UNKNOWN_EXPERIENCE"]["path"] == "experiences[1]"
    assert codes["UNKNOWN_EXPERIENCE"]["reference"] == "mission_fantome"


def test_highlight_index_beyond_the_catalog_is_refused(master):
    content = _grouped_cv()
    content["cv"]["experiences"][1]["bullets"][0]["sources"] = ["permanence_test:9"]

    report = validate_cv_content(content, master)

    issue = next(item for item in report["truth_issues"] if item["code"] == "SOURCE_OUT_OF_RANGE")
    assert issue["path"] == "experiences[1].bullets[0]"
    assert issue["reference"] == "permanence_test:9"


def test_bullet_without_source_is_a_truth_error(master):
    content = _grouped_cv()
    content["cv"]["experiences"][1]["bullets"][0].pop("sources")

    report = validate_cv_content(content, master)

    assert any(item["code"] == "BULLET_WITHOUT_SOURCE" for item in report["truth_issues"])


def test_bullet_cannot_cite_a_mission_outside_its_block(master):
    content = _grouped_cv()
    content["cv"]["experiences"][1]["bullets"][0]["sources"] = ["boutique_fictive:0"]

    report = validate_cv_content(content, master)

    issue = next(
        item for item in report["truth_issues"] if item["code"] == "SOURCE_OUTSIDE_EXPERIENCE"
    )
    assert issue["reference"] == "boutique_fictive:0"


def test_group_leaning_on_an_undeclared_member_is_refused(master):
    content = _grouped_cv()
    content["cv"]["experiences"][0]["source_experience_ids"] = [
        "boutique_fictive",
        "permanence_test",
    ]

    report = validate_cv_content(content, master)

    issue = next(
        item for item in report["truth_issues"] if item["code"] == "UNDECLARED_GROUP_MEMBER"
    )
    assert issue["reference"] == "permanence_test"


def test_group_below_its_minimum_is_refused(master):
    content = _grouped_cv()
    content["cv"]["experiences"][0]["source_experience_ids"] = ["boutique_fictive"]
    content["cv"]["experiences"][0]["bullets"] = [
        {"text": "Catalogue WooCommerce inventé.", "sources": ["boutique_fictive:0"]}
    ]

    report = validate_cv_content(content, master)

    assert any(item["code"] == "GROUP_TOO_FEW_MEMBERS" for item in report["truth_issues"])


def test_unknown_skill_and_unknown_education_are_refused(master):
    content = _grouped_cv()
    content["cv"]["skills"][0]["items"].append("Kubernetes")
    content["cv"]["education"] = [{"title": "Doctorat inventé"}]

    report = validate_cv_content(content, master)

    codes = {item["code"] for item in report["truth_issues"]}
    assert {"UNKNOWN_SKILL", "UNKNOWN_EDUCATION"} <= codes


def test_composed_education_rendering_is_supported(master):
    """Le créateur rend les formations composées — année, niveau, statut et
    école ajoutés autour du titre — et le rendu reste couvert par
    person.education : l'écart de formatage ne doit pas produire un faux
    refus de vérité (cas réel du 22/09/2026, VAE CDA + Doranco)."""
    content = _grouped_cv()
    content["cv"]["education"] = [
        {
            "title": (
                "2019 — Titre professionnel Developpeur web (fictif) "
                "(niveau 5, en cours de passage)"
            )
        },
    ]

    report = validate_cv_content(content, master)

    assert not any(
        item["code"] == "UNKNOWN_EDUCATION" for item in report["truth_issues"]
    )


def test_education_rendering_with_an_invented_title_is_still_refused(master):
    """L'habillage ne pardonne pas un titre qui n'existe pas : le rendu composé
    d'une formation inventée reste un refus de vérité."""
    content = _grouped_cv()
    content["cv"]["education"] = [
        {"title": "2019 — Doctorat en Astrochimie (niveau 8, obtenue)"},
    ]

    report = validate_cv_content(content, master)

    assert any(
        item["code"] == "UNKNOWN_EDUCATION" for item in report["truth_issues"]
    )


def test_project_technology_must_belong_to_the_project(master):
    content = _grouped_cv()
    content["cv"]["projects"][0]["technologies"] = ["Kubernetes"]

    report = validate_cv_content(content, master)

    assert any(
        item["code"] == "UNKNOWN_PROJECT_TECHNOLOGY" for item in report["truth_issues"]
    )


def test_forbidden_claim_is_a_truth_error(master):
    content = _grouped_cv()
    content["cv"]["profile"] = "Expert du web inventé."

    report = validate_cv_content(content, master)

    assert any(item["code"] == "FORBIDDEN_CLAIM" for item in report["truth_issues"])


def test_unsourced_job_terms_are_never_introduced_by_the_validator(careco, master):
    """Une exigence non sourcée reste un écart honnête, jamais une compétence."""
    report = validate_cv_content(_grouped_cv(), master)

    assert report["ok"]
    rendered = json.dumps(report["content"], ensure_ascii=False).lower()
    for term in careco["unsourced_terms"]:
        assert term not in rendered


# --------------------------------------------------------------------------- #
# Gabarit : corrigeable, jamais corrigé en silence
# --------------------------------------------------------------------------- #


def test_long_bullet_is_a_format_error_not_a_truncation(master):
    content = _grouped_cv()
    long_text = "Catalogue WooCommerce inventé. " * 10
    content["cv"]["experiences"][0]["bullets"][0]["text"] = long_text

    report = validate_cv_content(content, master)

    assert report["truth_issues"] == []
    assert any(item["code"] == "BULLET_TOO_LONG" for item in report["format_issues"])
    assert content["cv"]["experiences"][0]["bullets"][0]["text"] == long_text


def test_non_antichronological_order_is_reported_not_reordered(master):
    content = _grouped_cv()
    content["cv"]["experiences"].reverse()
    before = copy.deepcopy(content["cv"]["experiences"])

    report = validate_cv_content(content, master)

    assert any(
        item["code"] == "EXPERIENCE_ORDER_NOT_ANTICHRONOLOGICAL"
        for item in report["format_issues"]
    )
    assert content["cv"]["experiences"] == before


def test_empty_experience_is_a_format_error_not_a_fallback_bullet(master):
    content = _grouped_cv()
    content["cv"]["experiences"][1]["bullets"] = []

    report = validate_cv_content(content, master)

    assert any(item["code"] == "EMPTY_EXPERIENCE" for item in report["format_issues"])
    assert content["cv"]["experiences"][1]["bullets"] == []


def test_cv_without_any_experience_is_a_truth_error(master):
    report = validate_cv_content({"cv": {"experiences": []}}, master)

    assert any(item["code"] == "EMPTY_CV" for item in report["truth_issues"])


def test_overloaded_skills_and_projects_are_format_errors(master):
    content = _grouped_cv()
    content["cv"]["skills"] = [
        {"title": f"Bloc {index}", "items": ["WordPress"]} for index in range(6)
    ]

    report = validate_cv_content(content, master)

    assert any(item["code"] == "TOO_MANY_SKILL_SECTIONS" for item in report["format_issues"])


# --------------------------------------------------------------------------- #
# Dates : ce que la source ne dit pas, le CV ne l'affirme pas
# --------------------------------------------------------------------------- #


def test_open_period_without_ongoing_is_a_source_issue(master):
    """Une fin absente est une inconnue, pas un « Aujourd'hui ».

    C'est le défaut du CV L'Atelier Digital : un freelance 2023-2024 rendu
    « 2023 – Aujourd'hui » et hissé en tête, parce que la source n'avait pas
    de fin et que personne ne le remarquait.
    """
    profil = copy.deepcopy(master)
    del profil["experience_groups"]["missions_techniques_2026"]["period"]["ongoing"]
    content = _grouped_cv()
    before = copy.deepcopy(content)

    report = validate_cv_content(content, profil)

    codes = [item["code"] for item in report["source_issues"]]
    assert codes == ["SOURCE_END_DATE_UNCONFIRMED"]
    assert report["source_issues"][0]["path"] == "experiences[0]"
    assert report["truth_issues"] == []
    assert report["format_issues"] == []
    assert content == before


def test_declared_ongoing_period_is_rendered_and_sorted_as_current(master):
    """« ongoing » déclaré : rendu « Aujourd'hui » et trié en tête, sans erreur."""
    from cv_generator.job_analyzer import _period_sort_key
    from cv_generator.utils import period_to_text

    en_cours = master["experience_groups"]["missions_techniques_2026"]["period"]
    fermee = master["experience_catalog"]["permanence_test"]["period"]

    assert period_to_text(en_cours) == "2026-03 – Aujourd'hui"
    assert period_to_text(fermee) == "2024-01 – 2025-12"
    assert _period_sort_key(en_cours) > _period_sort_key(fermee)
    assert validate_cv_content(_grouped_cv(), master)["source_issues"] == []


def test_unknown_end_never_outranks_a_more_recent_experience():
    """Une fin inconnue ne promeut plus l'expérience en première ligne."""
    from cv_generator.job_analyzer import _period_sort_key
    from cv_generator.utils import period_to_text

    inconnue = {"start": "2023", "end": None}
    recente = {"start": "2026-03", "end": "2026-08"}

    assert _period_sort_key(inconnue) < _period_sort_key(recente)
    assert period_to_text(inconnue) == "2023 – (fin à confirmer)"


def test_ongoing_claim_backed_by_the_cited_proof_blames_the_source(master):
    """Puce et preuve disent « depuis » sur une période fermée : c'est la source."""
    profil = copy.deepcopy(master)
    profil["experience_catalog"]["permanence_test"]["highlights"][0] = (
        "Accompagnement d'usagers fictifs depuis 2024."
    )
    content = _grouped_cv()
    content["cv"]["experiences"][1]["bullets"][0]["text"] = (
        "Accompagnement d'usagers fictifs depuis 2024."
    )

    report = validate_cv_content(content, profil)

    assert [item["code"] for item in report["source_issues"]] == [
        "SOURCE_TEMPORAL_CLAIM_CONFLICT"
    ]
    assert report["source_issues"][0]["path"] == "experiences[1].bullets[0]"
    assert report["truth_issues"] == []


def test_ongoing_claim_invented_by_the_agent_is_a_truth_error(master):
    """La même phrase sans preuve qui la porte est une date ajoutée : bloquant."""
    content = _grouped_cv()
    content["cv"]["experiences"][1]["bullets"][0]["text"] = (
        "Accompagnement d'usagers fictifs, toujours actuellement en poste."
    )

    report = validate_cv_content(content, master)

    assert [item["code"] for item in report["truth_issues"]] == [
        "TEMPORAL_CLAIM_NOT_IN_SOURCE"
    ]
    assert report["source_issues"] == []
