"""Présentation d'un dossier : site web affiché ou non, titre du mail HTML.

Demande Cundo 18/11/2026 : varascundo.com ne doit plus être imposé, et le
mail HTML ne doit plus signer « Développeur web » pour un poste d'animateur.
"""
import json
from types import SimpleNamespace

from agents.application_email_agent import generate_application_email
from applications.mail_preview import preview
from applications.mail_template import dossier_mail_html, render_mail_html
from utils.presentation import (
    apply_website_line,
    contact_line,
    hidden_site_mentions,
    presentation_for,
    update_dossier_presentation,
)

RECO = SimpleNamespace(cv_name="CV Accueil", cv_id="accueil", reason="")

LETTRE = """Paris, le 18 novembre 2026

Objet : Candidature

Madame, Monsieur,

Je vous adresse ma candidature.

Cordialement,

Facundo Varas
Portfolio : varascundo.com
"""


# ── Défauts par famille et choix explicites ─────────────────────────────────

def test_defaut_site_affiche_pour_le_dev_et_masque_pour_l_animation():
    assert presentation_for({"job_family": "developpement"})["show_website"] is True
    for family in ("mediation_sociale", "mediation_numerique", "accueil", "logistique"):
        assert presentation_for({"job_family": family})["show_website"] is False


def test_le_choix_du_candidat_prime_sur_la_famille():
    assert presentation_for({"job_family": "developpement", "show_website": False})["show_website"] is False
    shown = presentation_for({"job_family": "accueil", "show_website": True, "website_url": "https://mediateur.varascundo.com/"})
    assert shown["show_website"] is True
    assert shown["website_url"] == "mediateur.varascundo.com"


def test_titre_par_defaut_selon_la_famille_et_titre_libre():
    assert "Développeur" in presentation_for({"job_family": "developpement"})["display_title"]
    assert "Développeur" not in presentation_for({"job_family": "mediation_sociale"})["display_title"]
    assert presentation_for({"display_title": "Animateur – accueil des publics"})["display_title"] == (
        "Animateur – accueil des publics"
    )


def test_adresse_invalide_retombe_sur_le_site_par_defaut():
    assert presentation_for({"website_url": "javascript:alert(1)"})["website_url"] == "varascundo.com"


# ── Ligne Portfolio : ajout, remplacement, retrait ──────────────────────────

def test_site_masque_retire_la_ligne_portfolio_et_rien_d_autre():
    out = apply_website_line(LETTRE, {"show_website": False})
    assert "Portfolio" not in out
    assert out == LETTRE.replace("Portfolio : varascundo.com\n", "")


def test_site_affiche_remplace_l_adresse():
    out = apply_website_line(LETTRE, {"show_website": True, "website_url": "mediateur.varascundo.com"})
    assert "Portfolio : mediateur.varascundo.com" in out
    assert out.count("Portfolio") == 1


def test_site_affiche_ajoute_la_ligne_sous_la_signature():
    sans = LETTRE.replace("Portfolio : varascundo.com\n", "")
    out = apply_website_line(sans, {"show_website": True, "website_url": "varascundo.com"})
    assert out.rstrip().endswith("Facundo Varas\nPortfolio : varascundo.com")


def test_mention_du_site_dans_le_texte_alors_qu_il_est_masque():
    hidden = {"show_website": False}
    assert hidden_site_mentions("Voir varascundo.com pour mes projets.", hidden)
    # un projet en sous-domaine reste citable
    assert not hidden_site_mentions("J'ai conçu mediateur.varascundo.com.", hidden)
    # l'adresse mail n'est pas le site
    assert not hidden_site_mentions("Écrivez-moi : contact@varascundo.com", hidden)


def test_bandeau_pdf():
    assert contact_line({"show_website": False}) == "Paris 20e · contact@varascundo.com"
    assert contact_line({"show_website": True, "website_url": "ia.varascundo.com"}).endswith("· ia.varascundo.com")


# ── Mail texte et HTML ──────────────────────────────────────────────────────

def test_mail_animation_sans_portfolio_ni_developpeur():
    job = {"title": "Animateur famille du centre socioculturel", "company": "Mairie", "job_family": "mediation_sociale"}
    mail = generate_application_email(job, RECO, {"name": "Facundo Varas"})
    assert "Portfolio" not in mail
    assert "Développeur" not in mail
    assert "CAP Petite Enfance" in mail


def test_mail_dev_garde_son_portfolio():
    job = {"title": "Développeur web", "company": "Agence", "job_family": "developpement"}
    assert "Portfolio : varascundo.com" in generate_application_email(job, RECO, {})


def test_html_sans_ligne_portfolio_n_affiche_aucun_site():
    corps = "Bonjour,\n\nJe postule.\n\nCV joint : CV Accueil\n\nCordialement,\nFacundo Varas"
    html = render_mail_html("Objet", corps, sender_email="x@y.fr")
    assert "Portfolio" not in html
    assert "varascundo.com" not in html


def test_titre_du_candidat_echappe_dans_le_html():
    html = render_mail_html("Objet", "Bonjour,\n\nTexte.", sender_email="x@y.fr", candidate_titre="Animateur <b>& accueil</b>")
    assert "Animateur &lt;b&gt;&amp; accueil&lt;/b&gt;" in html
    assert "Développeur web" not in html


# ── Dossier : mise à jour et aperçu identique à l'envoi ─────────────────────

def _dossier(tmp_path, job):
    (tmp_path / "job.json").write_text(json.dumps(job), encoding="utf-8")
    (tmp_path / "lettre_motivation.md").write_text(LETTRE, encoding="utf-8")
    (tmp_path / "mail_candidature.md").write_text(
        "Objet : Candidature — Animateur\n\nBonjour,\n\nJe postule.\n\nCV joint : CV\nPortfolio : varascundo.com\n\n"
        "Cordialement,\nFacundo Varas\n",
        encoding="utf-8",
    )
    return tmp_path


def test_mise_a_jour_du_dossier(tmp_path, monkeypatch):
    import applications.application_builder as builder

    monkeypatch.setattr(builder, "_write_letter_pdf", lambda *a, **k: None)
    d = _dossier(tmp_path, {"title": "Animateur", "job_family": "developpement"})
    result = update_dossier_presentation(d, {"show_website": False, "display_title": "Animateur – accueil des publics"})
    assert result["ok"] and result["presentation"]["show_website"] is False
    job = json.loads((d / "job.json").read_text(encoding="utf-8"))
    assert job["show_website"] is False and job["display_title"] == "Animateur – accueil des publics"
    assert "Portfolio" not in (d / "lettre_motivation.md").read_text(encoding="utf-8")
    assert "Portfolio" not in (d / "mail_candidature.md").read_text(encoding="utf-8")
    assert "Portfolio" not in result["lettre"] and "Portfolio" not in result["mail"]


def test_mise_a_jour_refuse_une_adresse_invalide(tmp_path, monkeypatch):
    import pytest

    d = _dossier(tmp_path, {"title": "x"})
    with pytest.raises(ValueError):
        update_dossier_presentation(d, {"show_website": True, "website_url": "pas une adresse"})


def test_apercu_identique_au_html_envoye(tmp_path, monkeypatch):
    from applications.send import _mail_parts

    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.setenv("EMAIL_SENDER", "contact@varascundo.com")
    d = _dossier(tmp_path, {"title": "Animateur", "display_title": "Animateur – accueil des publics"})
    result = preview(d)
    subject, body = _mail_parts(d / "mail_candidature.md")
    assert result["html"] == dossier_mail_html(d, subject, body, sender_email="contact@varascundo.com")
    assert "Animateur – accueil des publics" in result["html"]
