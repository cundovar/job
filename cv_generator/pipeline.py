from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .ai_agents import AICVPipeline, AgentClient
from .exporters import cv_to_html, cv_to_markdown, cv_to_pdf
from .utils import load_json, save_json


def _trace_item(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "agent": payload.get("agent"),
        **(payload.get("agent_run") or {}),
    }


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
    final_cv = agents.revise(job, master, plan, draft, review)
    final_review = agents.review(job, master, plan, final_cv)

    trace = {
        "pipeline": "ai_cv_pipeline_v2",
        "job": {
            "title": job.get("title"),
            "company": job.get("company"),
            "url": job.get("url"),
            "description_chars": len(str(job.get("description") or "")),
        },
        "runs": [
            _trace_item(plan),
            _trace_item(draft),
            _trace_item(review),
            _trace_item(final_cv),
            _trace_item(final_review),
        ],
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
    (output_dir / "cv_draft.md").write_text(cv_to_markdown(draft), encoding="utf-8")
    save_json(output_dir / "cv_review.json", review)
    save_json(output_dir / "cv_final_review.json", final_review)
    save_json(output_dir / "cv_final.json", final_cv)
    save_json(output_dir / "cv_agent_trace.json", trace)
    (output_dir / "cv_final.md").write_text(cv_to_markdown(final_cv), encoding="utf-8")
    (output_dir / "cv_canva_copy.md").write_text(cv_to_markdown(final_cv, canva=True), encoding="utf-8")
    (output_dir / "cv_final.html").write_text(cv_to_html(final_cv), encoding="utf-8")
    cv_to_pdf(final_cv, output_dir / "cv_final.pdf")

    return {
        "ok": True,
        "pipeline": trace["pipeline"],
        "application_dir": str(Path(application_dir)),
        "cv_dir": str(output_dir),
        "selected_base_variant": plan.get("selected_base_variant"),
        "target_title": final_cv.get("cv", {}).get("title") or plan.get("target_title"),
        "quality_score": final_review.get("quality_score"),
        "ats_score": final_review.get("ats_score"),
        "status": final_review.get("status"),
        "agent_runs": trace["runs"],
        "files": {
            "plan": str(output_dir / "cv_adaptation_plan.json"),
            "draft": str(output_dir / "cv_draft.json"),
            "draft_md": str(output_dir / "cv_draft.md"),
            "review": str(output_dir / "cv_review.json"),
            "final_review": str(output_dir / "cv_final_review.json"),
            "final_json": str(output_dir / "cv_final.json"),
            "agent_trace": str(output_dir / "cv_agent_trace.json"),
            "final_md": str(output_dir / "cv_final.md"),
            "canva_copy": str(output_dir / "cv_canva_copy.md"),
            "html": str(output_dir / "cv_final.html"),
            "pdf": str(output_dir / "cv_final.pdf"),
        },
    }
