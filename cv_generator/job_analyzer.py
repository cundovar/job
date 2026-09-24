from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .utils import compact_items, contains_any, flatten_skills, job_text, normalize


def _period_sort_key(period: Dict[str, Any] | None) -> Tuple[str, str]:
    """Return a sortable (end, start) key, with declared ongoing work first.

    « En cours » se déclare (``ongoing``) : une fin simplement absente est une
    inconnue, pas un présent. La traiter comme un présent faisait remonter une
    expérience ancienne au-dessus des missions récentes — c'est ce qui plaçait
    un freelance commencé en 2023 en première ligne du CV.
    """
    if not isinstance(period, dict):
        return ("0000-00", "0000-00")

    def normalized(value: Any, month: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return "0000-00"
        return raw if "-" in raw else f"{raw}-{month}"

    start = normalized(period.get("start"), "01")
    if period.get("end"):
        end = normalized(period.get("end"), "12")
    elif period.get("ongoing") is True and period.get("start"):
        end = "9999-12"
    else:
        # Fin inconnue : on ne promeut rien, la date de début fait foi.
        end = start
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

    # A teaching role remains a teaching CV even when the subject is technical:
    # otherwise each mention of PHP/Symfony/React wrongly routes it to fullstack.
    teaching_terms = ["formateur", "formation", "enseignant", "apprenants", "pédagogie", "pedagogie"]
    web_development_terms = ["developpement web", "développement web", "html", "css", "javascript", "react", "php", "symfony", "wordpress"]
    if contains_any(text, teaching_terms) and contains_any(text, web_development_terms):
        return next((variant for variant in variants if variant.get("id") == "formateur_developpement_web"), {})

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


def _max_experiences(master: Dict[str, Any], variant_id: str) -> int:
    constraints = master.get("layout_constraints", {})
    by_variant = constraints.get("max_experiences_by_variant", {})
    return int(by_variant.get(variant_id, constraints.get("max_experiences", 4)))


def _experience_plan(job: Dict[str, Any], selected: Dict[str, Any], master: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Catalogue de suggestions noté, remis tel quel à l'agent analyste.

    Ce n'est plus une sélection : aucun quota, aucun minimum, aucune expérience
    forcée, aucun emplacement réservé. Python note la proximité entre chaque
    expérience et l'annonce, puis laisse l'agent retenir ce qu'il juge utile.
    """
    text = job_text(job)
    # Une expérience retirée ne se suggère pas plus qu'elle ne se propose.
    catalog = {
        identifier: entry
        for identifier, entry in master.get("experience_catalog", {}).items()
        if not (isinstance(entry, dict) and entry.get("retired") is True)
    }
    variant_id = selected.get("id", "")
    preferred = master.get("adaptation_rules", {}).get("experience_priority_by_variant", {}).get(variant_id, [])
    excluded = set(
        master.get("adaptation_rules", {})
        .get("excluded_experiences_by_variant", {})
        .get(variant_id, [])
    )
    refs = selected.get("experience_refs", [])
    ordered_ids = []
    for exp_id in preferred + refs + list(catalog.keys()):
        if exp_id in catalog and exp_id not in ordered_ids:
            ordered_ids.append(exp_id)
    suggestions = []
    for exp_id in ordered_ids:
        if exp_id in excluded:
            continue
        exp = catalog[exp_id]
        matched_tags = [tag for tag in exp.get("tags", []) if normalize(tag) in text]
        trigger_tags = exp.get("selection_triggers", exp.get("tags", []))
        matched_triggers = [tag for tag in trigger_tags if normalize(tag) in text]
        visibility = str(exp.get("visibility") or "default")
        # La visibilité conditionnelle est une règle du profil maître, pas une
        # préférence éditoriale : elle reste appliquée.
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
        matching_indexes = [
            index
            for index, item in enumerate(highlights)
            if any(token in text for token in normalize(item).split() if len(token) > 4)
        ]
        suggestions.append(
            {
                "experience_id": exp_id,
                "priority": score,
                "selection_role": exp.get("cv_role", "core"),
                "reason": (
                    f"Recoupe les mots-clés de l'annonce ({', '.join(matched_tags[:3])})."
                    if matched_tags
                    else "Aucun recoupement direct avec l'annonce."
                ),
                "matching_highlight_indexes": matching_indexes,
                "highlights": compact_items(
                    [highlights[index] for index in matching_indexes] or highlights[:3],
                    limit=3,
                    max_chars=145,
                ),
            }
        )
    suggestions.sort(key=lambda item: item["priority"], reverse=True)
    return suggestions


def _build_adaptation_strategy(
    job: Dict[str, Any],
    variant_id: str,
    priority_keywords: List[str],
    master: Dict[str, Any],
) -> Dict[str, Any]:
    """Index déterministe des preuves disponibles, sans décision éditoriale.

    Ne choisit plus ni projet, ni regroupement, ni ordre des sections : ces
    trois décisions reviennent à l'agent analyste.
    """
    text = job_text(job)
    evidence_matches = []
    for evidence_id, evidence in master.get("evidence_catalog", {}).items():
        terms = [
            *evidence.get("technologies", []),
            *evidence.get("capabilities", []),
            *evidence.get("usable_for", []),
        ]
        matched_terms = [term for term in terms if normalize(term) and normalize(term) in text]
        if not matched_terms:
            continue
        evidence_matches.append({
            "requirement": matched_terms[0],
            "evidence_id": evidence_id,
            "project_ids": [
                project_id
                for project_id in evidence.get("source_project_ids", [])
                if project_id in master.get("project_catalog", {})
            ],
            "experience_ids": [
                experience_id
                for experience_id in evidence.get("source_experience_ids", [])
                if experience_id in master.get("experience_catalog", {})
            ],
            "matched_terms": compact_items(matched_terms, limit=6),
        })
    return {
        "critical_requirements": [
            {"requirement": keyword, "importance": "high"}
            for keyword in priority_keywords[:6]
        ],
        "evidence_matches": evidence_matches,
        "suggested_section_order": ["profile", "skills", "experiences", "projects", "education"],
    }


def analyze_job_for_cv(job: Dict[str, Any], master: Dict[str, Any]) -> Dict[str, Any]:
    """Préanalyse consultative : ce que Python constate, jamais ce qu'il impose."""
    selected = _select_variant(job, master)
    variant_id = selected.get("id", "webmaster")
    title_variants = master.get("positioning", {}).get("title_variants", {})
    target_title = title_variants.get(variant_id) or selected.get("title") or "Développeur web / Webmaster"
    keywords = _priority_keywords(job, selected, master)
    strategy = _build_adaptation_strategy(job, variant_id, keywords, master)
    text = job_text(job)
    skills_to_reduce = []
    for skill, confidence in master.get("skills_confidence", {}).items():
        if confidence in {"bases", "notions", "notions à pratique selon projet"} and normalize(skill) not in text:
            skills_to_reduce.append(skill)
    # Les consignes éditoriales viennent du profil maître, plus d'une liste de
    # variantes codée dans ce fichier.
    guidance = master.get("adaptation_rules", {}).get("editorial_guidance_by_variant", {}).get(variant_id, {})
    warnings = []
    if isinstance(guidance, dict):
        for key in ("experience_policy", "project_policy", "public_proof"):
            if guidance.get(key):
                warnings.append(str(guidance[key]))
    if contains_any(text, ["expert", "senior", "bac+5", "lead"]):
        warnings.append("Vérifier que le CV ne survend pas le niveau réel demandé par l'annonce.")
    return {
        "agent": "cv_job_analyzer",
        "selected_base_variant": variant_id,
        "target_title": target_title,
        "positioning": master.get("positioning", {}).get("summary_variants", {}).get(variant_id, selected.get("profile", "")),
        "priority_keywords": keywords,
        "experience_suggestions": _experience_plan(job, selected, master),
        **strategy,
        "available_skills": flatten_skills(selected.get("skills", {})),
        "skills_to_reduce": compact_items(skills_to_reduce, limit=8),
        "warnings": compact_items(warnings, limit=8),
    }
