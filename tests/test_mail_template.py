"""Tests du rendu HTML des mails (applications/mail_template.py)."""

from applications.mail_template import parse_mail_body, render_mail_html

CORPS = """Bonjour,

Je vous adresse une candidature spontanée en tant que Développeur web / Intégrateur au sein de Agence Web Pro.

Développeur web et webmaster freelance (PHP/Symfony, Vue.js/React, WordPress/CMS), mon parcours combine gestion de sites, développement web, formation et automatisation IA.

CV joint : Webmaster / Administrateur de sites web
Portfolio : varascundo.com

Je me tiens à votre disposition pour un échange.

Cordialement,
Facundo Varas (Cundo)"""


def test_parse_split_the_edited_body_into_template_zones():
    zones = parse_mail_body(CORPS)
    assert zones["salutation"] == "Bonjour,"
    assert zones["cv_intitule"] == "Webmaster / Administrateur de sites web"
    assert zones["portfolio_url"] == "https://varascundo.com"
    assert zones["formule"] == "Cordialement,"
    assert zones["cloture"] and "disposition" in zones["cloture"]
    joined = " ".join(zones["paragraphes"])
    assert "Agence Web Pro" in joined
    assert "PHP/Symfony" in joined
    # la signature est rendue par le gabarit, jamais doublée dans les paragraphes
    assert not any("Facundo Varas" in p for p in zones["paragraphes"])


def test_render_produces_the_full_email_shell():
    html = render_mail_html(
        "Candidature spontanée — Développeur web / Intégrateur",
        CORPS,
        sender_email="contact@varascundo.com",
    )
    assert html.startswith("<!DOCTYPE html>")
    assert "Candidature spontanée — Développeur web / Intégrateur" in html
    assert "contact@varascundo.com" in html
    assert "Webmaster / Administrateur de sites web" in html
    assert "https://varascundo.com" in html
    assert "{%" not in html and "{{" not in html  # gabarit entièrement rendu


def test_render_never_loses_free_edited_text():
    corps = CORPS.replace(
        "mon parcours combine gestion de sites, développement web, formation et automatisation IA.",
        "J'ai dirigé la refonte de trois sites institutionnels en 2024.",
    )
    html = render_mail_html("Objet", corps, sender_email="x@y.fr")
    assert "refonte de trois sites institutionnels" in html
