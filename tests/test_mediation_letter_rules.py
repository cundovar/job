"""Règles éditoriales mécaniques des lettres médiation numérique.

Le prompt (config/agent_redacteur_lettres.md) porte les règles rédactionnelles ;
ce module vérifie la ceinture de sécurité code : ligne « Portfolio » retirée,
mention de DevDoc signalée sans réécriture silencieuse.
"""

from agents.motivation_letter_agent import (
    apply_mediation_poste_rules,
    is_mediation_poste,
)

LETTRE_MEDIATEUR = """Paris, le 16 octobre 2026

Mairie de Test

Objet : Candidature au poste de Médiateur numérique

Madame, Monsieur,

Je souhaite rejoindre votre équipe et cite Mediateur (mediateur.varascundo.com).

Cordialement,

Facundo Varas
Portfolio : varascundo.com
Email : contact@varascundo.com"""

LETTRE_DEV = """Paris, le 16 octobre 2026

Agence Test

Objet : Candidature au poste de Développeur web

Madame, Monsieur,

Je développe en Symfony et React.

Cordialement,

Facundo Varas
Portfolio : varascundo.com
Email : contact@varascundo.com"""


def test_titres_mediation_detectes():
    assert is_mediation_poste("Médiateur numérique")
    assert is_mediation_poste("Conseiller Numérique")
    assert is_mediation_poste("Médiateur/Médiatrice emploi et numérique")
    assert is_mediation_poste("médiateur conseiller numérique")


def test_titres_hors_mediation_non_detectes():
    assert not is_mediation_poste("Développeur web PHP/Symfony")
    assert not is_mediation_poste("Webmaster WordPress")
    assert not is_mediation_poste("Formateur Développement Web")
    assert not is_mediation_poste("")


def test_ligne_portfolio_retiree_pour_poste_mediation():
    lettre = apply_mediation_poste_rules(LETTRE_MEDIATEUR, "Médiateur numérique")
    assert "Portfolio" not in lettre
    assert "Email : contact@varascundo.com" in lettre
    assert "Facundo Varas" in lettre


def test_ligne_portfolio_conservee_hors_mediation():
    lettre = apply_mediation_poste_rules(LETTRE_DEV, "Développeur web PHP/Symfony")
    assert "Portfolio : varascundo.com" in lettre


def test_mention_devdoc_avertit_sans_reecriture(caplog):
    lettre_devdoc = LETTRE_MEDIATEUR.replace(
        "cite Mediateur (mediateur.varascundo.com)",
        "cite DevDoc, une plateforme pédagogique",
    )
    with caplog.at_level("WARNING"):
        lettre = apply_mediation_poste_rules(lettre_devdoc, "Conseiller Numérique")
    # Jamais de réécriture silencieuse : le texte reste, l'avertissement sort.
    assert "DevDoc" in lettre
    assert any("DevDoc" in rec.message and "Mediateur" in rec.message for rec in caplog.records)


def test_titre_vide_ne_plante_pas():
    assert apply_mediation_poste_rules(LETTRE_DEV, "") == LETTRE_DEV
