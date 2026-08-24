"""
Application email generation — Cundo's style.
"""
from __future__ import annotations

from typing import Any, Dict


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
    portfolio = profile.get("portfolio", "varascundo.com")
    title = _job_value(job, "title", "le poste proposé")
    company = _job_value(job, "company")
    company_line = f" au sein de {company}" if company else ""

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
    else:
        pitch = (
            "Développeur web et webmaster freelance (PHP/Symfony, Vue.js/React, "
            "WordPress/CMS), mon parcours combine gestion de sites, développement web, "
            "formation et automatisation IA."
        )

    return "\n".join([
        f"Objet : Candidature — {title}",
        "",
        "Bonjour,",
        "",
        f"Je vous adresse ma candidature pour le poste de {title}{company_line}.",
        "",
        pitch,
        "",
        f"CV joint : {recommendation.cv_name}",
        f"Portfolio : {portfolio}",
        "",
        "Je me tiens à votre disposition pour un échange.",
        "",
        "Cordialement,",
        str(candidate_name),
        "",
    ])
