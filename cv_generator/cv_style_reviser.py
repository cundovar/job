from __future__ import annotations

import copy
from typing import Any, Dict

from .utils import compact_items, normalize


def revise_cv_style(master: Dict[str, Any], plan: Dict[str, Any], draft: Dict[str, Any], review: Dict[str, Any]) -> Dict[str, Any]:
    final = copy.deepcopy(draft)
    final["agent"] = "cv_style_reviser"
    final["source_draft_agent"] = draft.get("agent")
    cv = final.get("cv", {})
    constraints = master.get("layout_constraints", {})
    max_profile = int(constraints.get("max_profile_chars", 240))
    profile = cv.get("profile", "")
    if len(profile) > max_profile:
        cv["profile"] = profile[: max_profile - 1].rstrip(" ,;:") + "…"
    # Add missing keywords conservatively to skill sections if already present in master skills/confidence.
    known = {normalize(skill): skill for skill in master.get("skills_confidence", {}).keys()}
    missing = [kw for kw in review.get("missing_keywords", []) if normalize(kw) in known]
    if missing:
        sections = cv.setdefault("skills", [])
        if sections:
            first_items = sections[0].setdefault("items", [])
            for kw in missing:
                if kw not in first_items:
                    first_items.append(kw)
            first_items[:] = compact_items(first_items, limit=8)
    max_bullets = int(constraints.get("max_bullets_per_experience", 3))
    max_chars = int(constraints.get("max_bullet_chars", 145))
    for exp in cv.get("experiences", []):
        exp["bullets"] = compact_items(exp.get("bullets", []), max_bullets, max_chars)
    # Strip forbidden claims if any appeared in final text by exact phrase replacement.
    for claim in master.get("forbidden_claims", []):
        claim_norm = normalize(claim)
        if not claim_norm:
            continue
        if claim in cv.get("profile", ""):
            cv["profile"] = cv["profile"].replace(claim, "").replace("  ", " ").strip()
        for exp in cv.get("experiences", []):
            exp["bullets"] = [bullet.replace(claim, "").replace("  ", " ").strip(" -") for bullet in exp.get("bullets", [])]
    final["review_applied"] = {
        "initial_quality_score": review.get("quality_score"),
        "initial_ats_score": review.get("ats_score"),
        "status_before_revision": review.get("status"),
        "notes": "Corrections automatiques conservatrices : longueur, bullets, mots-clés connus uniquement.",
    }
    return final
