"""
Build local application packages for selected job offers.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from agents.application_email_agent import generate_application_email
from agents.motivation_letter_agent import generate_motivation_letter
from agents.summary_agent import summarize_job

from .cv_selector import CVRecommendation, recommend_cv


@dataclass(frozen=True)
class ApplicationPackage:
    directory: str
    resume_path: str
    cv_recommendation_path: str
    motivation_letter_path: str
    application_email_path: str
    metadata_path: str
    recommended_cv: CVRecommendation


def _slugify(value: str, max_length: int = 80) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )
    lowered = without_accents.lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return (cleaned or "candidature")[:max_length].strip("-")


def _job_value(job: Dict[str, Any], key: str, default: str = "") -> str:
    value = job.get(key, default)
    return str(value).strip() if value is not None else default


def _build_application_dir(
    job: Dict[str, Any],
    output_dir: str,
    created_at: datetime,
) -> Path:
    date_prefix = created_at.strftime("%Y-%m-%d")
    company = _slugify(_job_value(job, "company", "entreprise"), max_length=40)
    title = _slugify(_job_value(job, "title", "poste"), max_length=55)
    directory = Path(output_dir) / f"{date_prefix}_{company}_{title}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _offer_resume_markdown(job: Dict[str, Any], recommendation: CVRecommendation) -> str:
    analysis = job.get("ai_analysis", {}) if isinstance(job.get("ai_analysis"), dict) else {}
    summary = summarize_job(job)
    description = _job_value(job, "description")
    short_description = description[:1200].strip()
    if len(description) > len(short_description):
        short_description += "..."

    return "\n".join(
        [
            "# Resume de l'offre",
            "",
            f"- Poste : {_job_value(job, 'title', 'Non renseigne')}",
            f"- Entreprise : {_job_value(job, 'company', 'Non renseignee')}",
            f"- Lieu : {_job_value(job, 'location', 'Non renseigne')}",
            f"- Contrat : {_job_value(job, 'contract_type', 'Non renseigne')}",
            f"- Source : {_job_value(job, 'source', 'Non renseignee')}",
            f"- URL : {_job_value(job, 'url', 'Non renseignee')}",
            f"- Score : {job.get('score', 'Non renseigne')}",
            f"- Recommandation : {analysis.get('recommandation', 'Non renseignee')}",
            "",
            "## CV conseille",
            "",
            f"- Profil : {recommendation.cv_name}",
            f"- Fichier : {recommendation.cv_path}",
            f"- Raison : {recommendation.reason}",
            "",
            summary.to_markdown(),
            "",
            "## Description courte",
            "",
            short_description or "Description non renseignee.",
            "",
        ]
    )


def _cv_recommendation_text(recommendation: CVRecommendation) -> str:
    return "\n".join(
        [
            f"CV conseille : {recommendation.cv_name}",
            f"Fichier : {recommendation.cv_path}",
            f"Score de correspondance : {recommendation.score}",
            f"Mots-cles detectes : {', '.join(recommendation.matched_keywords) or 'Aucun'}",
            f"Raison : {recommendation.reason}",
            "",
        ]
    )


def build_application_package(
    job: Dict[str, Any],
    output_dir: str = "output/applications",
    user_profile: Dict[str, Any] | None = None,
) -> ApplicationPackage:
    created_at = datetime.now(timezone.utc)
    recommendation = recommend_cv(job)
    directory = _build_application_dir(job, output_dir, created_at)

    resume_path = directory / "offre_resume.md"
    cv_recommendation_path = directory / "cv_recommande.txt"
    motivation_letter_path = directory / "lettre_motivation.md"
    application_email_path = directory / "mail_candidature.md"
    metadata_path = directory / "metadata.json"

    resume_path.write_text(_offer_resume_markdown(job, recommendation), encoding="utf-8")
    cv_recommendation_path.write_text(_cv_recommendation_text(recommendation), encoding="utf-8")
    motivation_letter_path.write_text(
        generate_motivation_letter(job, recommendation, user_profile),
        encoding="utf-8",
    )
    application_email_path.write_text(
        generate_application_email(job, recommendation, user_profile),
        encoding="utf-8",
    )

    metadata = {
        "job_title": _job_value(job, "title"),
        "company": _job_value(job, "company"),
        "score": job.get("score"),
        "source": _job_value(job, "source"),
        "url": _job_value(job, "url"),
        "status": "ready_to_apply",
        "created_at": created_at.isoformat(),
        "recommended_cv": asdict(recommendation),
        "files": {
            "resume": str(resume_path),
            "cv_recommendation": str(cv_recommendation_path),
            "motivation_letter": str(motivation_letter_path),
            "application_email": str(application_email_path),
            "metadata": str(metadata_path),
        },
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    return ApplicationPackage(
        directory=str(directory),
        resume_path=str(resume_path),
        cv_recommendation_path=str(cv_recommendation_path),
        motivation_letter_path=str(motivation_letter_path),
        application_email_path=str(application_email_path),
        metadata_path=str(metadata_path),
        recommended_cv=recommendation,
    )
