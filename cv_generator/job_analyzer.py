from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .utils import compact_items, contains_any, flatten_skills, job_text, normalize


def _period_sort_key(period: Dict[str, Any] | None) -> Tuple[str, str]:
    """Return a sortable (end, start) key, with ongoing work first."""
    if not isinstance(period, dict):
        return ("0000-00", "0000-00")

    def normalized(value: Any, month: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return "0000-00"
        return raw if "-" in raw else f"{raw}-{month}"

    start = normalized(period.get("start"), "01")
    end = "9999-12" if period.get("end") is None and period.get("start") else normalized(period.get("end"), "12")
    return (end, start)


def _score_variant(text: str, variant: Dict[str, Any], master: Dict[str, Any]) -> int:
    rules = master.get("adaptation_rules", {}).get("variant_selection", {})
    keywords = list(rules.get(variant.get("id", ""), []))
    keywords.extend(variant.get("tags", []))
    keywords.extend(flatten_skills(variant.get("skills", {})))
    score = 0
    for keyword in keywords:
        if normalize(keyword) in text:
            score += 3 if keyword in rules.get(variant.get("id", ""), []) else 1
    return score


def _select_variant(job: Dict[str, Any], master: Dict[str, Any]) -> Dict[str, Any]:
    text = job_text(job)
    variants = master.get("cv_variants", [])
    scored: List[Tuple[int, int, Dict[str, Any]]] = []
    default_priority = master.get("positioning", {}).get("default_priority", [])
    for variant in variants:
        priority_penalty = default_priority.index(variant["id"]) if variant.get("id") in default_priority else 99
        scored.append((_score_variant(text, variant, master), -priority_penalty, variant))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return scored[0][2] if scored else {}


def _priority_keywords(job: Dict[str, Any], selected: Dict[str, Any], master: Dict[str, Any]) -> List[str]:
    text = job_text(job)
    skills = flatten_skills(selected.get("skills", {}))
    explicit = []
    for keyword in skills + selected.get("tags", []):
        norm = normalize(keyword)
        if norm and any(part in text for part in norm.split()[:2]):
            explicit.append(str(keyword))
    # A few important job terms may not be in current variant skills.
    common_terms = [
        "WordPress", "WooCommerce", "CMS", "maintenance", "administration", "RGAA",
        "accessibilité", "SEO", "React", "Vue.js", "Symfony", "PHP", "API REST",
        "formation", "pédagogie", "support utilisateurs", "documentation", "n8n",
        "automatisation", "Microsoft 365", "Jira", "Git", "Docker"
    ]
    for term in common_terms:
        if normalize(term) in text:
            explicit.append(term)
    return compact_items(explicit, limit=14)


def _select_experience_mix(
    plan: List[Dict[str, Any]],
    catalog: Dict[str, Any],
    max_experiences: int,
) -> List[Dict[str, Any]]:
    """Reserve the last of four slots for one relevant human/creative experience."""
    if max_experiences < 4:
        return plan[:max_experiences]
    complementary = [
        item
        for item in plan
        if catalog.get(item.get("experience_id"), {}).get("cv_role") == "complementary"
    ]
    if not complementary:
        return plan[:max_experiences]
    core = [item for item in plan if item not in complementary]
    return core[: max_experiences - 1] + complementary[:1]


def _max_experiences(master: Dict[str, Any], variant_id: str) -> int:
    constraints = master.get("layout_constraints", {})
    by_variant = constraints.get("max_experiences_by_variant", {})
    return int(by_variant.get(variant_id, constraints.get("max_experiences", 4)))


def _merge_preferred_skills(
    skills: Dict[str, Any],
    master: Dict[str, Any],
    variant_id: str,
) -> Dict[str, List[str]]:
    preferred = master.get("adaptation_rules", {}).get("preferred_skills_by_variant", {}).get(variant_id, {})
    result: Dict[str, List[str]] = {}
    seen = set()
    # A configured preference replaces the broad variant catalogue for the
    # deterministic pre-analysis. The AI still has access to every truthful
    # skill and may select different ones when the advert warrants it.
    for source in ((preferred,) if preferred else (skills,)):
        for section, items in source.items():
            target = result.setdefault(str(section), [])
            for item in items if isinstance(items, list) else []:
                key = normalize(item)
                if key and key not in seen:
                    target.append(str(item))
                    seen.add(key)
    return {section: items for section, items in result.items() if items}


def _experience_plan(job: Dict[str, Any], selected: Dict[str, Any], master: Dict[str, Any]) -> List[Dict[str, Any]]:
    text = job_text(job)
    catalog = master.get("experience_catalog", {})
    variant_id = selected.get("id", "")
    preferred = master.get("adaptation_rules", {}).get("experience_priority_by_variant", {}).get(variant_id, [])
    refs = selected.get("experience_refs", [])
    ordered_ids = []
    for exp_id in preferred + refs + list(catalog.keys()):
        if exp_id in catalog and exp_id not in ordered_ids:
            ordered_ids.append(exp_id)
    plan = []
    for exp_id in ordered_ids:
        exp = catalog[exp_id]
        matched_tags = [tag for tag in exp.get("tags", []) if normalize(tag) in text]
        trigger_tags = exp.get("selection_triggers", exp.get("tags", []))
        matched_triggers = [tag for tag in trigger_tags if normalize(tag) in text]
        visibility = str(exp.get("visibility") or "default")
        if visibility.startswith("only_") and not matched_triggers:
            continue
        score = 0
        if exp_id in preferred:
            score += 6
        if exp_id in refs:
            score += 3
        score += 2 * len(matched_tags)
        if visibility.startswith("only_") and matched_triggers:
            score += 8
        highlights = exp.get("highlights", [])
        picked = []
        for item in highlights:
            item_text = normalize(item)
            if any(token in text for token in item_text.split() if len(token) > 4):
                picked.append(item)
        if not picked:
            picked = highlights[:3]
        if score > 0:
            plan.append({
                "experience_id": exp_id,
                "priority": score,
                "selection_role": exp.get("cv_role", "core"),
                "reason": f"Expérience alignée avec la variante {variant_id} et les mots-clés de l'annonce.",
                "highlights": compact_items(picked, limit=3, max_chars=145),
            })
    # Relevance determines which experiences are kept. Their presentation is
    # then always reverse chronological, as recruiters expect on a CV.
    plan.sort(key=lambda item: item["priority"], reverse=True)
    max_experiences = _max_experiences(master, variant_id)
    selected_plan = _select_experience_mix(plan, catalog, max_experiences)

    # Some variants have experiences that are essential evidence for the target role.
    # Guarantee them after relevance selection, then sort the final mix by date.
    required_ids = master.get("adaptation_rules", {}).get("required_experiences_by_variant", {}).get(variant_id, [])
    selected_ids = {item.get("experience_id") for item in selected_plan}
    plan_by_id = {item.get("experience_id"): item for item in plan}
    for required_id in required_ids:
        if required_id in selected_ids or required_id not in catalog:
            continue
        required_item = plan_by_id.get(required_id)
        if required_item is None:
            exp = catalog[required_id]
            required_item = {
                "experience_id": required_id,
                "priority": 100,
                "selection_role": exp.get("cv_role", "core"),
                "reason": f"Expérience requise pour la variante {variant_id}.",
                "highlights": compact_items(exp.get("highlights", []), limit=3, max_chars=145),
            }
        if len(selected_plan) >= max_experiences:
            replace_index = next(
                (i for i in range(len(selected_plan) - 1, -1, -1)
                 if selected_plan[i].get("experience_id") not in required_ids),
                None,
            )
            if replace_index is not None:
                selected_plan.pop(replace_index)
        if len(selected_plan) < max_experiences:
            selected_plan.append(required_item)
            selected_ids.add(required_id)

    selected_plan.sort(
        key=lambda item: _period_sort_key(catalog.get(item["experience_id"], {}).get("period")),
        reverse=True,
    )
    return selected_plan



def _build_adaptation_strategy(
    job: Dict[str, Any],
    variant_id: str,
    experience_plan: List[Dict[str, Any]],
    priority_keywords: List[str],
    master: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a deterministic, grounded brief consumed by all CV agents."""
    text = job_text(job)
    selected_ids = [item.get("experience_id") for item in experience_plan]
    evidence_matches = []
    selected_projects = []
    for evidence_id, evidence in master.get("evidence_catalog", {}).items():
        terms = [
            *evidence.get("technologies", []),
            *evidence.get("capabilities", []),
            *evidence.get("usable_for", []),
        ]
        matched_terms = [term for term in terms if normalize(term) and normalize(term) in text]
        if not matched_terms:
            continue
        distinctive_terms = {
            "agents ia", "agent ia", "mcp", "n8n", "python", "scraping",
            "wordpress", "generation controlee", "correction automatique",
            "orchestration d agents", "orchestration multi agents",
        }
        has_distinctive_match = any(normalize(term) in distinctive_terms for term in matched_terms)
        project_ids = [
            project_id
            for project_id in evidence.get("source_project_ids", [])
            if project_id in master.get("project_catalog", {})
        ]
        experience_ids = [
            experience_id
            for experience_id in evidence.get("source_experience_ids", [])
            if experience_id in master.get("experience_catalog", {})
        ]
        evidence_matches.append({
            "requirement": matched_terms[0],
            "evidence_id": evidence_id,
            "project_ids": project_ids,
            "experience_ids": experience_ids,
            "matched_terms": compact_items(matched_terms, limit=6),
        })
        if variant_id in {"automatisation", "formateur_ia"} and has_distinctive_match:
            for project_id in project_ids:
                if project_id not in selected_projects:
                    selected_projects.append(project_id)

    presentation = {"experience_display_mode": "individual"}
    for group_id, group in master.get("experience_groups", {}).items():
        if variant_id not in group.get("allowed_variants", []):
            continue
        member_ids = [item for item in selected_ids if item in group.get("member_ids", [])]
        for alternatives in group.get("mutually_exclusive_sets", []):
            present = [item for item in member_ids if item in alternatives]
            member_ids = [item for item in member_ids if item not in alternatives] + present[:1]
        if len(member_ids) >= int(group.get("min_selected_members", 2)):
            presentation = {
                "experience_display_mode": group.get("display_mode", "grouped_missions"),
                "experience_group_id": group_id,
                "member_ids": member_ids,
            }
            break

    # Projects lead only when the advert is explicitly technical/agentic.
    # Human-facing mediation and general training must lead with experience.
    explicit_ai_terms = [
        "agent ia", "agents ia", "agentic", "mcp", "orchestration",
        "automatisation", "n8n", "workflow", "harnais",
    ]
    ai_first = variant_id == "automatisation" or (
        variant_id in {"fullstack", "frontend"} and contains_any(text, explicit_ai_terms)
    )
    return {
        "critical_requirements": [
            {"requirement": keyword, "importance": "high"}
            for keyword in priority_keywords[:6]
        ],
        "evidence_matches": evidence_matches,
        "presentation_strategy": presentation,
        "section_order": (
            ["profile", "skills", "projects", "experiences", "education"]
            if ai_first else
            ["profile", "skills", "experiences", "projects", "education"]
        ),
        "selected_projects": selected_projects[:2],
    }


def analyze_job_for_cv(job: Dict[str, Any], master: Dict[str, Any]) -> Dict[str, Any]:
    selected = _select_variant(job, master)
    variant_id = selected.get("id", "webmaster")
    title_variants = master.get("positioning", {}).get("title_variants", {})
    target_title = title_variants.get(variant_id) or selected.get("title") or "Développeur web / Webmaster"
    keywords = _priority_keywords(job, selected, master)
    experience_plan = _experience_plan(job, selected, master)
    strategy = _build_adaptation_strategy(job, variant_id, experience_plan, keywords, master)
    # These are suggestions for the AI analyzer, not content that Python may
    # force back into the final CV.
    selected_skills = _merge_preferred_skills(selected.get("skills", {}), master, variant_id)
    text = job_text(job)
    skills_to_reduce = []
    for skill, confidence in master.get("skills_confidence", {}).items():
        if confidence in {"bases", "notions", "notions à pratique selon projet"} and normalize(skill) not in text:
            skills_to_reduce.append(skill)
    warnings = []
    if variant_id in {"webmaster", "wordpress", "formateur_developpement_web", "formateur_ia", "accessibilite"}:
        warnings.append("Ne pas présenter Cundo comme développeur full-stack pur : adapter l'accroche au poste.")
    if contains_any(text, ["expert", "senior", "bac+5", "lead"]):
        warnings.append("Vérifier que le CV ne survend pas le niveau réel demandé par l'annonce.")
    return {
        "agent": "cv_job_analyzer",
        "selected_base_variant": variant_id,
        "target_title": target_title,
        "positioning": master.get("positioning", {}).get("summary_variants", {}).get(variant_id, selected.get("profile", "")),
        "priority_keywords": keywords,
        "experience_plan": experience_plan,
        **strategy,
        "skills_to_emphasize": selected_skills,
        "skills_to_reduce": compact_items(skills_to_reduce, limit=8),
        "warnings": warnings,
    }
