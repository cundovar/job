from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .ai_agents import AICVPipeline, AgentClient
from .ats_exporter import cv_to_ats_html, cv_to_ats_pdf
from .ats_validator import validate_ats_pdf
from .cv_assessment import build_cv_assessment
from .exporters import cv_to_html, cv_to_pdf
from .utils import load_json, save_json

MAX_AUTOMATIC_REVISION_ROUNDS = 3
REVISION_STATUSES = {"needs_revision", "needs_minor_revision"}


def _trace_item(payload: Dict[str, Any]) -> Dict[str, Any]:
    item = {
        "agent": payload.get("agent"),
        **(payload.get("agent_run") or {}),
    }
    if "evidence_coverage" in payload:
        item["evidence_coverage"] = payload.get("evidence_coverage")
    return item


def _apply_final_review_status(assessment: Dict[str, Any], final_review: Dict[str, Any]) -> Dict[str, Any]:
    assessment["final_ai_review"] = {
        "status": final_review.get("status"),
        "quality_score": final_review.get("quality_score"),
        "ats_score": final_review.get("ats_score"),
        "verdict": final_review.get("verdict"),
        "evidence_coverage": final_review.get("evidence_coverage", []),
    }
    if final_review.get("status") == "needs_revision":
        assessment["overall_status"] = "review"
    return assessment


def prepare_custom_cv(
    job: Dict[str, Any],
    application_dir: str | Path,
    master_path: str | Path = "data/cv_master_profile.json",
    llm_client: AgentClient | None = None,
) -> Dict[str, Any]:
    """Build a grounded CV through four real AI roles plus Python guardrails."""
    master = load_json(master_path)
    output_dir = Path(application_dir) / "cv"
    output_dir.mkdir(parents=True, exist_ok=True)

    agents = AICVPipeline(llm_client)
    plan = agents.analyze(job, master)
    draft = agents.create(job, master, plan)
    review = agents.review(job, master, plan, draft)
    final_cv = draft
    final_review = review
    trace_runs = [_trace_item(plan), _trace_item(draft), _trace_item(review)]
    automatic_revision_rounds = 0
    while (
        final_review.get("status") in REVISION_STATUSES
        and automatic_revision_rounds < MAX_AUTOMATIC_REVISION_ROUNDS
    ):
        final_cv = agents.revise(job, master, plan, final_cv, final_review)
        final_review = agents.review(job, master, plan, final_cv)
        automatic_revision_rounds += 1
        trace_runs.extend([_trace_item(final_cv), _trace_item(final_review)])

    automatic_corrections_exhausted = final_review.get("status") in REVISION_STATUSES

    trace = {
        "pipeline": "ai_cv_pipeline_v3",
        "job": {
            "title": job.get("title"),
            "company": job.get("company"),
            "url": job.get("url"),
            "description_chars": len(str(job.get("description") or "")),
            "candidate_instructions_present": bool(
                str(job.get("candidate_instructions") or "").strip()
            ),
            "candidate_instructions_chars": len(
                str(job.get("candidate_instructions") or "").strip()
            ),
        },
        "runs": trace_runs,
        "correction_retried": automatic_revision_rounds > 0,
        "automatic_revision_rounds": automatic_revision_rounds,
        "automatic_corrections_exhausted": automatic_corrections_exhausted,
        "automatic_revision_limit": MAX_AUTOMATIC_REVISION_ROUNDS,
        "python_guardrails": [
            "identifiants d'expériences limités au JSON maître",
            "intitulés, organisations, dates, diplômes et contacts recopiés depuis la source",
            "chaque puce reliée à un ou plusieurs highlights sources",
            "compétences filtrées sur les libellés autorisés",
            "contraintes Canva et affirmations interdites contrôlées en Python",
        ],
    }

    save_json(output_dir / "cv_adaptation_plan.json", plan)
    save_json(output_dir / "cv_draft.json", draft)
    save_json(output_dir / "cv_review.json", review)
    save_json(output_dir / "cv_final_review.json", final_review)
    save_json(output_dir / "cv_final.json", final_cv)
    save_json(output_dir / "cv_agent_trace.json", trace)
    (output_dir / "cv_final.html").write_text(cv_to_html(final_cv), encoding="utf-8")
    cv_to_pdf(final_cv, output_dir / "cv_final.pdf")
    (output_dir / "cv_ats.html").write_text(cv_to_ats_html(final_cv), encoding="utf-8")
    cv_to_ats_pdf(final_cv, output_dir / "cv_ats.pdf")
    parseability = validate_ats_pdf(output_dir / "cv_ats.pdf", final_cv)
    assessment = build_cv_assessment(job, master, plan, final_cv, parseability=parseability)
    assessment = _apply_final_review_status(assessment, final_review)
    save_json(output_dir / "cv_assessment.json", assessment)

    return {
        "ok": True,
        "pipeline": trace["pipeline"],
        "application_dir": str(Path(application_dir)),
        "cv_dir": str(output_dir),
        "selected_base_variant": plan.get("selected_base_variant"),
        "target_title": final_cv.get("cv", {}).get("title") or plan.get("target_title"),
        "quality_score": assessment["human_quality"]["score"],
        "ats_score": assessment["match"]["score"],
        "status": assessment["overall_status"],
        "assessment": assessment,
        "agent_runs": trace["runs"],
        "files": {
            "plan": str(output_dir / "cv_adaptation_plan.json"),
            "draft": str(output_dir / "cv_draft.json"),
            "review": str(output_dir / "cv_review.json"),
            "final_review": str(output_dir / "cv_final_review.json"),
            "final_json": str(output_dir / "cv_final.json"),
            "agent_trace": str(output_dir / "cv_agent_trace.json"),
            "html": str(output_dir / "cv_final.html"),
            "pdf": str(output_dir / "cv_final.pdf"),
            "ats_html": str(output_dir / "cv_ats.html"),
            "ats_pdf": str(output_dir / "cv_ats.pdf"),
            "assessment": str(output_dir / "cv_assessment.json"),
        },
    }
