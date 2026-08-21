"""
Motivation letter generation — personalised for Facundo "Cundo" Varas.
Uses the full user_profile from criteria.yaml.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .summary_agent import summarize_job


def _job_value(job: Dict[str, Any], key: str, default: str = "") -> str:
    value = job.get(key, default)
    return str(value).strip() if value is not None else default


def _analysis_value(job: Dict[str, Any], key: str, default: str = "") -> str:
    analysis = job.get("ai_analysis", {})
    if not isinstance(analysis, dict):
        return default
    value = analysis.get(key, default)
    return str(value).strip() if value else default


def _pick_experiences(job: Dict, profile: Dict) -> list[str]:
    """Select 2-3 most relevant experiences for this job."""
    experiences = profile.get("experiences", [])
    title = _job_value(job, "title", "").lower()
    desc = _job_value(job, "description", "").lower()

    scored = []
    for exp in experiences:
        exp_l = exp.lower()
        score = 0
        if "symfony" in title and "symfony" in exp_l:
            score += 3
        if "wordpress" in title and "wordpress" in exp_l:
            score += 3
        if "formateur" in title and ("formateur" in exp_l or "pole" in exp_l):
            score += 3
        if "ia" in title and ("n8n" in exp_l or "ia" in exp_l):
            score += 3
        if "vue" in title and "vue" in exp_l:
            score += 2
        if any(kw in desc for kw in ["ess", "association", "insertion", "impact"]):
            if "insertion" in exp_l:
                score += 2
        scored.append((score, exp))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [exp for _, exp in scored[:3]]


def generate_motivation_letter(
    job: Dict[str, Any],
    recommendation: Any,
    user_profile: Dict[str, Any] | None = None,
) -> str:
    profile = user_profile or {}
    summary = summarize_job(job)
    candidate_name = profile.get("name", "Facundo Varas")
    portfolio = profile.get("portfolio", "varascundo.com")
    company = _job_value(job, "company", "votre structure")
    title = _job_value(job, "title", "le poste proposé")
    location = _job_value(job, "location", "")
    angle = _analysis_value(job, "angle_motivation")
    interesting_points = summary.why_interesting[:3]
    risks = summary.risks[:2]
    experiences = _pick_experiences(job, profile)

    # Accroche contextualisée
    has_ess = any(
        kw in f"{title} {_job_value(job, 'description', '')} {company}".lower()
        for kw in ["ess", "association", "fondation", "insertion", "impact social", "culture", "environnement"]
    )
    intro_values = ""
    if has_ess:
        intro_values = (
            " Les valeurs de votre structure — "
            "ancrées dans l'impact social — résonnent avec mon parcours."
        )

    lines = [
        "# Lettre de motivation",
        "",
        "Madame, Monsieur,",
        "",
        (
            f" Développeur full-stack freelance basé à Paris, "
            f"je vous propose ma candidature pour le poste de {title} "
            f"au sein de {company}.{intro_values}"
        ),
        "",
    ]

    # Paragraphe technique : expériences pertinentes
    if experiences:
        lines.append("Mon parcours récent illustre cette adéquation :")
        lines.append("")
        for exp in experiences:
            lines.append(f"- {exp}")
        lines.append("")

    # Points d'accroche depuis l'analyse DeepSeek
    if interesting_points:
        lines.append(
            "Dans votre offre, je retrouve plusieurs points d'accroche : "
            + " ".join(interesting_points)
            + "."
        )
        lines.append("")

    if angle:
        lines.append(f"**Angle à valoriser :** {angle}")
        lines.append("")

    # CV recommandé
    lines.append(
        f"Pour ce poste, le CV conseillé est **{recommendation.cv_name}** "
        f"({recommendation.reason.lower()})."
    )
    lines.append("")

    # Points à anticiper
    if risks:
        lines.append(
            "**Point à anticiper en entretien :** "
            + " ".join(risks)
            + " Je peux clarifier ces éléments en les reliant à mon expérience "
            "globale et à ma capacité d'adaptation."
        )
        lines.append("")

    # Conclusion
    lines.extend([
        "Je serais heureux d'échanger avec vous pour vous présenter "
        "plus concrètement ma candidature et ma vision du poste.",
        "",
        "Cordialement,",
        str(candidate_name),
        f"Portfolio : {portfolio}",
        "",
    ])

    return "\n".join(lines)
