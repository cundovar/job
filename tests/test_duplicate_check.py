"""duplicate_check : le domaine tranche, le nom ne tranche que s'il est identique."""
import pytest

from company_analysis.duplicate import domain_of, duplicate_check, normalize_name, same_organisation


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.econovia.fr/contact", "econovia.fr"),
        ("econovia.fr", "econovia.fr"),
        ("HTTPS://Econovia.FR/", "econovia.fr"),
        ("", ""),
        ("pas une url", ""),
    ],
)
def test_domain_of_normalizes_or_admits_it_cannot(url, expected):
    assert domain_of(url) == expected


def test_normalize_name_drops_the_legal_form_only():
    assert normalize_name("Jaam SARL") == normalize_name("Jaam")
    assert normalize_name("Jaam") != normalize_name("Jaamix")


def test_same_domain_beats_different_names():
    reason = same_organisation(
        "https://econovia.fr", "Econovia", "https://www.econovia.fr/jobs", "Studio E."
    )
    assert "econovia.fr" in reason


def test_same_name_beats_different_domains():
    """Une candidature partie via une annonce porte l'URL de l'annonce."""
    reason = same_organisation(
        "https://econovia.fr", "Econovia", "https://welcometothejungle.com/x", "Econovia"
    )
    assert "même nom" in reason


def test_substring_names_are_two_organisations():
    assert same_organisation("https://jaam.fr", "Jaam", "https://jaamix.fr", "Jaamix") == ""


def test_check_separates_excluded_from_contacted(tmp_path):
    measured = duplicate_check(
        "https://econovia.fr",
        "Econovia",
        contacted=[{"company": "Econovia", "url": "https://une-annonce.fr/offre"}],
        registry=[
            {"nom": "Econovia", "site": "https://econovia.fr", "statut": "prioritaire"},
            {"nom": "Ailleurs", "site": "https://ailleurs.fr", "statut": "ecartee"},
        ],
    )

    assert measured["error"] is None and measured["evidence"]
    value = measured["value"]
    assert value["domain"] == "econovia.fr"
    assert len(value["contacted"]) == 1
    assert value["excluded"] == []
    assert len(value["known"]) == 1


def test_unknown_target_leaves_every_register_empty():
    measured = duplicate_check("https://inconnue.fr", "Inconnue")

    assert measured["value"]["contacted"] == []
    assert measured["value"]["excluded"] == []
    assert measured["value"]["known"] == []
    assert "aucun doublon" in measured["evidence"]
