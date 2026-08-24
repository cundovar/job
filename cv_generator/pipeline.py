from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .cv_creator import create_cv_draft
from .cv_quality_checker import review_cv
from .cv_style_reviser import revise_cv_style
from .exporters import cv_to_html, cv_to_markdown, cv_to_pdf
from .job_analyzer import analyze_job_for_cv
from .utils import load_json, save_json


def prepare_custom_cv(
    job: Dict[str, Any],
    application_dir: str | Path,
    master_path: str | Path = "data/cv_master_profile.json",
) -> Dict[str, Any]:
    master = load_json(master_path)
    output_dir = Path(application_dir) / "cv"
    output_dir.mkdir(parents=True, exist_ok=True)

    plan = analyze_job_for_cv(job, master)
    draft = create_cv_draft(job, master, plan)
    review = review_cv(job, master, plan, draft)
    final_cv = revise_cv_style(master, plan, draft, review)
    final_review = review_cv(job, master, plan, final_cv)

    save_json(output_dir / "cv_adaptation_plan.json", plan)
    save_json(output_dir / "cv_draft.json", draft)
    save_json(output_dir / "cv_review.json", review)
    save_json(output_dir / "cv_final_review.json", final_review)
    save_json(output_dir / "cv_final.json", final_cv)
    (output_dir / "cv_final.md").write_text(cv_to_markdown(final_cv), encoding="utf-8")
    (output_dir / "cv_canva_copy.md").write_text(cv_to_markdown(final_cv, canva=True), encoding="utf-8")
    (output_dir / "cv_final.html").write_text(cv_to_html(final_cv), encoding="utf-8")
    cv_to_pdf(final_cv, output_dir / "cv_final.pdf")

    return {
        "ok": True,
        "application_dir": str(Path(application_dir)),
        "cv_dir": str(output_dir),
        "selected_base_variant": plan.get("selected_base_variant"),
        "target_title": plan.get("target_title"),
        "quality_score": final_review.get("quality_score"),
        "ats_score": final_review.get("ats_score"),
        "status": final_review.get("status"),
        "files": {
            "plan": str(output_dir / "cv_adaptation_plan.json"),
            "draft": str(output_dir / "cv_draft.json"),
            "review": str(output_dir / "cv_review.json"),
            "final_review": str(output_dir / "cv_final_review.json"),
            "final_json": str(output_dir / "cv_final.json"),
            "final_md": str(output_dir / "cv_final.md"),
            "canva_copy": str(output_dir / "cv_canva_copy.md"),
            "html": str(output_dir / "cv_final.html"),
            "pdf": str(output_dir / "cv_final.pdf"),
        },
    }
