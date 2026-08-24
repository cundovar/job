from __future__ import annotations

from typing import Any, Dict, List

from .utils import compact_items, period_to_text


def _skills_sections(plan: Dict[str, Any], master: Dict[str, Any]) -> List[Dict[str, Any]]:
    constraints = master.get("layout_constraints", {})
    max_sections = int(constraints.get("max_skill_sections", 4))
    max_items = int(constraints.get("max_skill_items_total", 28))
    raw = plan.get("skills_to_emphasize", {})
    sections = []
    used = 0
    for section, items in raw.items():
        if not isinstance(items, list) or used >= max_items:
            continue
        remaining = max_items - used
        picked = compact_items(items, limit=min(8, remaining))
        if picked:
            sections.append({"title": section.replace("_", " / ").title(), "items": picked})
            used += len(picked)
        if len(sections) >= max_sections:
            break
    return sections


def _experiences(plan: Dict[str, Any], master: Dict[str, Any]) -> List[Dict[str, Any]]:
    catalog = master.get("experience_catalog", {})
    result = []
    max_bullets = int(master.get("layout_constraints", {}).get("max_bullets_per_experience", 3))
    max_chars = int(master.get("layout_constraints", {}).get("max_bullet_chars", 145))
    for item in plan.get("experience_plan", []):
        exp = catalog.get(item.get("experience_id"), {})
        bullets = compact_items(item.get("highlights", exp.get("highlights", [])), max_bullets, max_chars)
        result.append({
            "id": item.get("experience_id"),
            "organization": exp.get("organization", ""),
            "title": exp.get("title", ""),
            "period": period_to_text(exp.get("period")),
            "bullets": bullets,
            "links": exp.get("links", [])[:2],
        })
    return result


def _projects(plan: Dict[str, Any], master: Dict[str, Any]) -> List[Dict[str, Any]]:
    variant = plan.get("selected_base_variant")
    max_projects = int(master.get("layout_constraints", {}).get("max_projects", 1))
    projects = []
    for project_id, project in master.get("project_catalog", {}).items():
        if variant in {"automatisation", "formateur_ia", "wordpress", "webmaster"} or any(
            kw in plan.get("priority_keywords", []) for kw in project.get("technologies", [])
        ):
            projects.append({
                "id": project_id,
                "title": project.get("title", ""),
                "year": project.get("year"),
                "description": project.get("description", ""),
                "technologies": project.get("technologies", []),
            })
    return projects[:max_projects]


def create_cv_draft(job: Dict[str, Any], master: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    person = master.get("person", {})
    variant_id = plan.get("selected_base_variant", "webmaster")
    profile = plan.get("positioning") or master.get("positioning", {}).get("summary_variants", {}).get(variant_id, "")
    max_profile = int(master.get("layout_constraints", {}).get("max_profile_chars", 420))
    if len(profile) > max_profile:
        profile = profile[: max_profile - 1].rstrip(" ,;:") + "…"
    cv = {
        "title": plan.get("target_title", "Développeur web / Webmaster"),
        "profile": profile,
        "contact": person.get("contact", {}),
        "location": person.get("location", "Paris / Île-de-France"),
        "skills": _skills_sections(plan, master),
        "experiences": _experiences(plan, master),
        "projects": _projects(plan, master),
        "education": [edu for edu in person.get("education", []) if edu.get("visibility") != "only_if_relevant"][:2],
        "languages": person.get("languages", []),
    }
    return {
        "agent": "cv_creator",
        "generated_for": {
            "job_title": job.get("title"),
            "company": job.get("company"),
            "source_url": job.get("url"),
        },
        "base_variant": variant_id,
        "cv": cv,
        "canva_copy_blocks": {
            "title": cv["title"],
            "profile": cv["profile"],
            "skills": cv["skills"],
            "experiences": cv["experiences"],
            "projects": cv["projects"],
        },
    }
