"""
Application email generation — Cundo's style.
"""
from __future__ import annotations

from typing import Any, Dict

from utils.presentation import apply_attachment_lines, presentation_for


MAIL_NOTE_MAX = 1000


def _job_value(job: Dict[str, Any], key: str, default: str = "") -> str:
    value = job.get(key, default)
    return str(value).strip() if value is not None else default


def generate_application_email(
    job: Dict[str, Any],
    recommendation: Any,
    user_profile: Dict[str, Any] | None = None,
) -> str:
    profile = user_profile or {}
    candidate_name = profile.get("name", "Facundo Varas")
    # Site affiché ou non : choix du dossier (case « Ajouter un site web »),
    # sinon défaut de la famille du poste. Plus de varascundo.com imposé.
    presentation = presentation_for(job)
    portfolio = presentation["website_url"] if presentation["show_website"] else ""
    family = _job_value(job, "job_family")
    title = _job_value(job, "title", "le poste proposé")
    company = _job_value(job, "company")
    company_line = f" au sein de {company}" if company else ""
    # Sur la voie spontanée, aucune annonce n'existe : parler « du poste »
    # présuppose un recrutement en cours que l'entreprise n'a jamais publié.
    spontaneous = _job_value(job, "source") == "prospection_spontanee"

    # Pick 2-3 key strengths relevant to the job
    title_l = title.lower()
    if any(kw in title_l for kw in ["symfony", "php"]):
        pitch = (
            "Développeur full-stack PHP/Symfony avec une pratique de la qualité "
            "de code (PHPStan, PHPUnit, PSR-12), je suis également formateur web "
            "auprès de publics en insertion."
        )
    elif any(kw in title_l for kw in ["wordpress", "woocommerce"]):
        pitch = (
            "Développeur WordPress/WooCommerce (headless, custom themes), je mène "
            "actuellement un redesign complet en React pour une maison d'édition."
        )
    elif any(kw in title_l for kw in ["formateur", "enseignant", "pédagogie"]):
        pitch = (
            "Ancien encadrant technique en développement web auprès de publics "
            "en insertion, je conçois également des ressources pédagogiques "
            "interactives (DevDoc, 15+ technologies couvertes)."
        )
    elif family in {"mediation_sociale", "accueil"}:
        # Postes d'accueil, d'animation, de lien avec les familles : seuls
        # des faits du profil maître (CAP, Mairie de Chelles, Pôle S,
        # Bioconcept), sans technique.
        pitch = (
            "Titulaire d'un CAP Petite Enfance, j'ai été animateur périscolaire "
            "à la Mairie de Chelles, puis formateur auprès d'adultes en insertion "
            "au Pôle S. J'ai également assuré l'accueil et l'orientation de publics "
            "comme gardien et hôte d'accueil."
        )
    elif family == "mediation_numerique":
        pitch = (
            "Formateur auprès d'adultes en insertion au Pôle S, j'ai conçu "
            "Mediateur, un site gratuit de formation à la médiation numérique "
            "(mediateur.varascundo.com)."
        )
    else:
        pitch = (
            "Développeur web et webmaster freelance (PHP/Symfony, Vue.js/React, "
            "WordPress/CMS), mon parcours combine gestion de sites, développement web, "
            "formation et automatisation IA."
        )

    objet = (
        f"Objet : Candidature spontanée — {title}"
        if spontaneous
        else f"Objet : Candidature — {title}"
    )
    ouverture = (
        f"Je vous adresse une candidature spontanée en tant que {title}{company_line}."
        if spontaneous
        else f"Je vous adresse ma candidature pour le poste de {title}{company_line}."
    )
    # Phrase écrite par le candidat lui-même dans l'interface : insérée telle
    # quelle, jamais reformulée ni complétée. C'est sa parole, pas une
    # déduction du modèle — le mail reste un gabarit sans IA.
    note = _job_value(job, "mail_personal_note")[:MAIL_NOTE_MAX]
    note_block = [note, ""] if note else []

    return apply_attachment_lines("\n".join([
        objet,
        "",
        "Bonjour,",
        "",
        ouverture,
        "",
        pitch,
        "",
        *note_block,
        f"CV joint : {recommendation.cv_name}",
        *([f"Portfolio : {portfolio}"] if portfolio else []),
        "",
        "Je me tiens à votre disposition pour un échange.",
        "",
        "Cordialement,",
        str(candidate_name),
        "",
    ]), presentation)
