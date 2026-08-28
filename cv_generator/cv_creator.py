from __future__ import annotations

from typing import Any, Dict, List

from .utils import compact_items, normalize, period_to_text


def _education_for_job(job: Dict[str, Any], person: Dict[str, Any], plan: Dict[str, Any], limit: int = 4) -> List[Dict[str, Any]]:
    """Keep default studies and add conditional ones when the job matches their tags."""
    job_text = normalize(" ".join(str(job.get(key) or "") for key in ("title", "description")))
    priority_text = normalize(" ".join(str(item) for item in plan.get("priority_keywords", [])))
    selected: List[Dict[str, Any]] = []
    conditional: List[tuple[int, Dict[str, Any]]] = []
    for education in person.get("education", []):
        if education.get("visibility") != "only_if_relevant":
            selected.append(education)
            continue
        tags = [normalize(tag) for tag in education.get("tags", [])]
        matches = sum(1 for tag in tags if tag and (tag in job_text or tag in priority_text))
        if matches:
            conditional.append((matches, education))
    conditional.sort(key=lambda item: item[0], reverse=True)
    # Entries marked as default describe the core professional path and must
    # never be displaced by conditional human/cultural education entries.
    remaining = max(0, limit - len(selected))
    return selected[:limit] + [education for _, education in conditional[:remaining]]


def _skills_sections(plan: Dict[str, Any], master: Dict[str, Any]) -> List[Dict[str, Any]]:
    constraints = master.get("layout_constraints", {})
    max_sections = int(constraints.get("max_skill_sections", 4))
    max_items = int(constraints.get("max_skill_items_total", 10))
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
            "selection_role": item.get("selection_role", "core"),
            "organization": exp.get("organization", ""),
            "title": exp.get("title", ""),
            "period": period_to_text(exp.get("period")),
            "bullets": bullets,
            "links": exp.get("links", [])[:2],
        })
    return result


def _projects(job: Dict[str, Any], plan: Dict[str, Any], master: Dict[str, Any]) -> List[Dict[str, Any]]:
    variant = plan.get("selected_base_variant")
    max_projects = int(master.get("layout_constraints", {}).get("max_projects", 1))
    variant_data = next((item for item in master.get("cv_variants", []) if item.get("id") == variant), {})
    project_refs = set(variant_data.get("project_refs", []))
    direct_job_text = normalize(" ".join(str(job.get(key) or "") for key in ("title", "description")))
    relevance_text = normalize(
        " ".join([direct_job_text, *[str(keyword) for keyword in plan.get("priority_keywords", [])]])
    )
    variant_keywords = [
        *master.get("adaptation_rules", {}).get("variant_selection", {}).get(variant, []),
        *variant_data.get("tags", []),
    ]
    variant_relevant = any(
        normalized and normalized in direct_job_text
        for normalized in (normalize(keyword) for keyword in variant_keywords)
    )
    required_ids = master.get("adaptation_rules", {}).get("required_projects_by_variant", {}).get(variant, [])

    def project_payload(project_id: str, project: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": project_id,
            "title": project.get("title", ""),
            "year": project.get("year"),
            "description": project.get("description", ""),
            "technologies": project.get("technologies", []),
            "links": project.get("links", [])[:2],
        }

    selected = []
    selected_ids = set()
    catalog = master.get("project_catalog", {})
    if variant_relevant:
        for project_id in required_ids:
            project = catalog.get(project_id)
            if project and project_id not in selected_ids:
                selected.append(project_payload(project_id, project))
                selected_ids.add(project_id)
            if len(selected) >= max_projects:
                return selected

    projects = []
    for project_id, project in catalog.items():
        if project_id in selected_ids:
            continue
        keywords = [*project.get("tags", []), *project.get("technologies", [])]
        normalized_keywords = [normalize(keyword) for keyword in keywords]
        matches = sum(1 for keyword in normalized_keywords if keyword and keyword in relevance_text)
        preferred = variant_relevant and variant in project.get("preferred_for", [])
        referenced = variant_relevant and project_id in project_refs
        score = matches * 3 + (5 if preferred else 0) + (8 if referenced else 0)
        if score > 0:
            projects.append((score, project_payload(project_id, project)))
    projects.sort(key=lambda item: (item[0], item[1].get("year") or 0), reverse=True)
    selected.extend(project for _, project in projects[: max_projects - len(selected)])
    return selected


def create_cv_draft(job: Dict[str, Any], master: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    person = master.get("person", {})
    variant_id = plan.get("selected_base_variant", "webmaster")
    profile = plan.get("positioning") or master.get("positioning", {}).get("summary_variants", {}).get(variant_id, "")
    max_profile = int(master.get("layout_constraints", {}).get("max_profile_chars", 240))
    if len(profile) > max_profile:
        profile = profile[: max_profile - 1].rstrip(" ,;:") + "…"
    cv = {
        "title": plan.get("target_title", "Développeur web / Webmaster"),
        "profile": profile,
        "contact": person.get("contact", {}),
        "location": person.get("location", "Paris / Île-de-France"),
        "skills": _skills_sections(plan, master),
        "experiences": _experiences(plan, master),
        "projects": _projects(job, plan, master),
        "education": _education_for_job(
            job,
            person,
            plan,
            limit=int(master.get("layout_constraints", {}).get("max_education_items", 4)),
        ),
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
