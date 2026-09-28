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
from agents.motivation_letter_agent import generate_motivation_letter_with_report
from agents.summary_agent import summarize_job

from .cv_selector import CVRecommendation, recommend_cv


@dataclass(frozen=True)
class ApplicationPackage:
    directory: str
    job_path: str
    resume_path: str
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


def _offer_resume_markdown(job: Dict[str, Any]) -> str:
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
            summary.to_markdown(),
            "",
            "## Description courte",
            "",
            short_description or "Description non renseignee.",
            "",
        ]
    )


def _write_letter_pdf(motivation_letter_path: Path, directory: Path) -> Path | None:
    # Le PDF part en pièce jointe avec le CV : un échec d'export ne fait pas
    # échouer le dossier, le .md reste la source de vérité de la lettre.
    lettre_pdf_path = directory / "lettre_motivation.pdf"
    try:
        from cv_generator.exporters import lettre_to_pdf

        lettre_to_pdf(motivation_letter_path, lettre_pdf_path)
    except Exception:
        return None
    return lettre_pdf_path


def _consignes_metadata(job: Dict[str, Any], report: Dict[str, Any]) -> Dict[str, Any]:
    """Ce que le candidat a demandé, et ce que l'agent dit en avoir fait."""
    return {
        "lettre": _job_value(job, "candidate_instructions"),
        "mail_note": _job_value(job, "mail_personal_note"),
        "rapport": report,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_application_package(
    job: Dict[str, Any],
    output_dir: str = "output/applications",
    user_profile: Dict[str, Any] | None = None,
) -> ApplicationPackage:
    created_at = datetime.now(timezone.utc)
    recommendation = recommend_cv(job)
    directory = _build_application_dir(job, output_dir, created_at)

    job_path = directory / "job.json"
    resume_path = directory / "offre_resume.md"
    motivation_letter_path = directory / "lettre_motivation.md"
    application_email_path = directory / "mail_candidature.md"
    metadata_path = directory / "metadata.json"

    job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    resume_path.write_text(_offer_resume_markdown(job), encoding="utf-8")
    letter, report = generate_motivation_letter_with_report(job, recommendation, user_profile)
    motivation_letter_path.write_text(letter, encoding="utf-8")
    lettre_pdf_path = _write_letter_pdf(motivation_letter_path, directory)
    application_email_path.write_text(
        generate_application_email(job, recommendation, user_profile),
        encoding="utf-8",
    )

    files = {
        "job": str(job_path),
        "resume": str(resume_path),
        "motivation_letter": str(motivation_letter_path),
        "application_email": str(application_email_path),
        "metadata": str(metadata_path),
    }
    if lettre_pdf_path is not None:
        files["motivation_letter_pdf"] = str(lettre_pdf_path)

    metadata = {
        "job_title": _job_value(job, "title"),
        "company": _job_value(job, "company"),
        "score": job.get("score"),
        "source": _job_value(job, "source"),
        "url": _job_value(job, "url"),
        "status": "ready_to_apply",
        "created_at": created_at.isoformat(),
        "recommended_cv": asdict(recommendation),
        "files": files,
        "consignes": _consignes_metadata(job, report),
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    return ApplicationPackage(
        directory=str(directory),
        job_path=str(job_path),
        resume_path=str(resume_path),
        motivation_letter_path=str(motivation_letter_path),
        application_email_path=str(application_email_path),
        metadata_path=str(metadata_path),
        recommended_cv=recommendation,
    )


class RegenerationRefused(RuntimeError):
    """La régénération toucherait un dossier qu'on n'a plus le droit de modifier."""


def _recommendation_from_metadata(metadata: Dict[str, Any], job: Dict[str, Any]) -> Any:
    raw = metadata.get("recommended_cv")
    if isinstance(raw, dict):
        try:
            return CVRecommendation(**raw)
        except TypeError:
            pass
    return recommend_cv(job)


def regenerate_letter_and_email(
    directory: str | Path,
    consignes: str,
    mail_note: str,
    user_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Réécrit lettre + mail d'un dossier existant avec de nouvelles consignes.

    Les consignes sont enregistrées dans ``job.json`` (même champ que la
    chaîne CV lit), la lettre repasse par l'agent, le mail par son gabarit.
    Le contenu qui partira change : l'approbation tombe, comme pour tout
    changement de destinataires ou de pièces jointes. Les éditions manuelles
    précédentes de la lettre et du mail sont remplacées — c'est le sens
    même d'une régénération, et le front le fait confirmer avant.
    """
    directory = Path(directory)
    job_path = directory / "job.json"
    metadata_path = directory / "metadata.json"
    if not job_path.is_file() or not metadata_path.is_file():
        raise RegenerationRefused(f"Dossier incomplet : {directory.name}")
    job = json.loads(job_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    consignes = str(consignes or "").strip()[:2000]
    mail_note = str(mail_note or "").strip()[:1000]
    for key, value in (("candidate_instructions", consignes), ("mail_personal_note", mail_note)):
        if value:
            job[key] = value
        else:
            job.pop(key, None)

    recommendation = _recommendation_from_metadata(metadata, job)
    # La lettre d'abord : si l'agent échoue, rien n'est réécrit sur disque.
    letter, report = generate_motivation_letter_with_report(job, recommendation, user_profile)
    email = generate_application_email(job, recommendation, user_profile)

    job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    motivation_letter_path = directory / "lettre_motivation.md"
    motivation_letter_path.write_text(letter, encoding="utf-8")
    (directory / "mail_candidature.md").write_text(email, encoding="utf-8")
    lettre_pdf_path = _write_letter_pdf(motivation_letter_path, directory)

    files = metadata.get("files") if isinstance(metadata.get("files"), dict) else {}
    if lettre_pdf_path is not None:
        files["motivation_letter_pdf"] = str(lettre_pdf_path)
    else:
        files.pop("motivation_letter_pdf", None)
    metadata["files"] = files
    metadata["consignes"] = _consignes_metadata(job, report)
    metadata["status"] = "ready_to_apply"
    metadata["approval_updated_at"] = datetime.now(timezone.utc).isoformat()
    metadata.pop("approval_recipients_hash", None)
    temporary = metadata_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(metadata_path)
    return {"id": directory.name, "consignes": metadata["consignes"]}
