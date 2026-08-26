from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .utils import flatten_skills, job_text, normalize


DEFAULT_CONFIG_PATH = "config/cv_assessment.json"


class CVAssessmentConfigError(ValueError):
    """Raised when the assessment configuration cannot produce stable scores."""


def load_assessment_config(path: str | Path = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_assessment_config(config)
    return config


def validate_assessment_config(config: Dict[str, Any]) -> None:
    for key in ("match_weights", "human_quality_weights"):
        weights = config.get(key)
        if not isinstance(weights, dict) or not weights:
            raise CVAssessmentConfigError(f"Configuration absente ou invalide: {key}")
        if any(not isinstance(value, int) or value < 0 for value in weights.values()):
            raise CVAssessmentConfigError(f"Les poids de {key} doivent être des entiers positifs.")
        if sum(weights.values()) != 100:
            raise CVAssessmentConfigError(f"Les poids de {key} doivent totaliser 100.")


def _status(checks: Iterable[Dict[str, Any]], empty: str = "pass") -> str:
    values = [str(item.get("status") or "review") for item in checks]
    if "fail" in values:
        return "fail"
    if "review" in values:
        return "review"
    return empty


def _candidate_eligibility(master: Dict[str, Any]) -> Dict[str, Any]:
    person = master.get("person", {})
    eligibility = person.get("eligibility", {})
    return eligibility if isinstance(eligibility, dict) else {}


def _profile_value_status(value: Any) -> str:
    if value is True:
        return "pass"
    if value is False:
        return "fail"
    return "review"


def evaluate_eligibility(
    job: Dict[str, Any],
    master: Dict[str, Any],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    text = job_text(job)
    candidate = _candidate_eligibility(master)
    checks: List[Dict[str, Any]] = []
    for check_id, patterns in config.get("eligibility_checks", {}).items():
        matched = [pattern for pattern in patterns if normalize(pattern) in text]
        if not matched:
            continue
        raw = candidate.get(check_id)
        if isinstance(raw, dict):
            value = raw.get("value")
            evidence = raw.get("evidence")
        else:
            value = raw
            evidence = None
        status = _profile_value_status(value)
        checks.append(
            {
                "id": check_id,
                "status": status,
                "requirement": matched[0],
                "reason": (
                    "Critère confirmé dans le profil."
                    if status == "pass"
                    else "Critère incompatible avec le profil."
                    if status == "fail"
                    else "Information absente ou insuffisante dans le profil."
                ),
                "evidence": evidence,
            }
        )
    return {
        "status": _status(checks),
        "checks": checks,
        "missing": [item["id"] for item in checks if item["status"] == "review"],
    }


def _cv_payload(final_cv: Dict[str, Any]) -> Dict[str, Any]:
    payload = final_cv.get("cv")
    return payload if isinstance(payload, dict) else final_cv


def _cv_text(final_cv: Dict[str, Any]) -> str:
    cv = _cv_payload(final_cv)
    parts: List[str] = [str(cv.get("title") or ""), str(cv.get("profile") or "")]
    for section in cv.get("skills", []):
        parts.extend(str(item) for item in section.get("items", []))
    for experience in cv.get("experiences", []):
        parts.extend(
            [
                str(experience.get("title") or ""),
                str(experience.get("organization") or ""),
                *(str(item) for item in experience.get("bullets", [])),
            ]
        )
    for education in cv.get("education", []):
        parts.extend(str(value) for value in education.values() if not isinstance(value, (list, dict)))
    return normalize(" ".join(parts))


def _ratio_score(found: int, total: int) -> int:
    return 100 if total <= 0 else round(100 * found / total)


def _weighted_score(components: Dict[str, Dict[str, Any]], weights: Dict[str, int]) -> int:
    return round(sum(components[key]["score"] * weight for key, weight in weights.items()) / 100)


def _band(score: int, config: Dict[str, Any]) -> str:
    bands = config.get("bands", {})
    if score >= int(bands.get("strong", 85)):
        return "strong"
    if score >= int(bands.get("credible", 70)):
        return "credible"
    if score >= int(bands.get("weak", 55)):
        return "weak"
    return "poor"


def evaluate_match(
    job: Dict[str, Any],
    master: Dict[str, Any],
    plan: Dict[str, Any],
    final_cv: Dict[str, Any],
    eligibility: Dict[str, Any],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    cv = _cv_payload(final_cv)
    text = _cv_text(final_cv)
    keywords = [str(item) for item in plan.get("priority_keywords", []) if str(item).strip()]
    matched_keywords = [item for item in keywords if normalize(item) in text]
    planned_ids = [item.get("experience_id") for item in plan.get("experience_plan", [])]
    present_ids = {item.get("id") for item in cv.get("experiences", [])}
    matched_experiences = [item for item in planned_ids if item in present_ids]

    job_title_tokens = {token for token in normalize(job.get("title")).split() if len(token) > 3}
    cv_title = normalize(cv.get("title"))
    matched_title_tokens = [token for token in job_title_tokens if token in cv_title]

    job_norm = job_text(job)
    education_markers = ["diplome", "diplôme", "bac+", "certification", "rncp", "formation"]
    education_required = any(normalize(marker) in job_norm for marker in education_markers)
    education_present = bool(cv.get("education"))

    constraint_checks = eligibility.get("checks", [])
    constraint_score = 100
    if constraint_checks:
        constraint_score = round(
            sum(100 if item["status"] == "pass" else 0 if item["status"] == "fail" else 50 for item in constraint_checks)
            / len(constraint_checks)
        )

    components = {
        "required_skills": {
            "score": _ratio_score(len(matched_keywords), len(keywords)),
            "matched": matched_keywords,
            "missing": [item for item in keywords if item not in matched_keywords],
        },
        "experience_evidence": {
            "score": _ratio_score(len(matched_experiences), len(planned_ids)),
            "matched": matched_experiences,
            "missing": [item for item in planned_ids if item not in present_ids],
        },
        "role_context": {
            "score": _ratio_score(len(matched_title_tokens), len(job_title_tokens)),
            "matched": matched_title_tokens,
            "missing": sorted(job_title_tokens.difference(matched_title_tokens)),
        },
        "education_certifications": {
            "score": 100 if not education_required or education_present else 0,
            "matched": ["education"] if education_present else [],
            "missing": ["education_or_certification"] if education_required and not education_present else [],
        },
        "constraints": {
            "score": constraint_score,
            "matched": [item["id"] for item in constraint_checks if item["status"] == "pass"],
            "missing": [item["id"] for item in constraint_checks if item["status"] != "pass"],
        },
    }
    score = _weighted_score(components, config["match_weights"])
    return {"score": score, "band": _band(score, config), "components": components}


def evaluate_truthfulness(master: Dict[str, Any], final_cv: Dict[str, Any]) -> Dict[str, Any]:
    cv = _cv_payload(final_cv)
    catalog = master.get("experience_catalog", {})
    allowed_skills = set(master.get("skills_confidence", {}).keys())
    for variant in master.get("cv_variants", []):
        allowed_skills.update(flatten_skills(variant.get("skills", {})))
    normalized_allowed = {normalize(item) for item in allowed_skills}
    issues: List[Dict[str, str]] = []
    for experience in cv.get("experiences", []):
        if experience.get("id") not in catalog:
            issues.append({"type": "unknown_experience", "value": str(experience.get("id"))})
    for section in cv.get("skills", []):
        for item in section.get("items", []):
            if normalize(item) not in normalized_allowed:
                issues.append({"type": "unknown_skill", "value": str(item)})
    text = _cv_text(final_cv)
    for claim in master.get("forbidden_claims", []):
        if normalize(claim) in text:
            issues.append({"type": "forbidden_claim", "value": str(claim)})
    return {
        "status": "fail" if issues else "pass",
        "issues": issues,
        "reason": "Contenu entièrement relié au profil maître." if not issues else "Contenu non autorisé détecté.",
    }


def evaluate_human_quality(
    master: Dict[str, Any],
    plan: Dict[str, Any],
    final_cv: Dict[str, Any],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    cv = _cv_payload(final_cv)
    constraints = master.get("layout_constraints", {})
    experiences = cv.get("experiences", [])
    planned = plan.get("experience_plan", [])
    grounding = final_cv.get("grounding", {}).get("experience_bullets", [])
    bullet_count = sum(len(item.get("bullets", [])) for item in experiences)
    long_bullets = sum(
        len(str(bullet)) > int(constraints.get("max_bullet_chars", 145))
        for item in experiences
        for bullet in item.get("bullets", [])
    )
    profile = str(cv.get("profile") or "")
    components = {
        "relevance": {"score": _ratio_score(len(experiences), len(planned))},
        "clarity": {"score": 100 if 80 <= len(profile) <= int(constraints.get("max_profile_chars", 420)) else 70},
        "evidence": {"score": _ratio_score(len(grounding), bullet_count)},
        "concision": {"score": max(0, 100 - long_bullets * 25)},
        "layout_readiness": {
            "score": 100
            if len(experiences) <= int(constraints.get("max_experiences", 4))
            else 50
        },
    }
    score = _weighted_score(components, config["human_quality_weights"])
    return {"score": score, "band": _band(score, config), "components": components}


def build_cv_assessment(
    job: Dict[str, Any],
    master: Dict[str, Any],
    plan: Dict[str, Any],
    final_cv: Dict[str, Any],
    parseability: Dict[str, Any] | None = None,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> Dict[str, Any]:
    config = load_assessment_config(config_path)
    eligibility = evaluate_eligibility(job, master, config)
    truthfulness = evaluate_truthfulness(master, final_cv)
    match = evaluate_match(job, master, plan, final_cv, eligibility, config)
    human_quality = evaluate_human_quality(master, plan, final_cv, config)
    parsing = parseability or {
        "status": "review",
        "reason": "Le PDF ATS n'a pas encore été validé.",
        "missing": ["ats_pdf_validation"],
    }
    controls = [eligibility.get("status"), parsing.get("status"), truthfulness.get("status")]
    if "fail" in controls:
        overall = "blocked"
    elif "review" in controls or match["score"] < int(config["bands"]["credible"]):
        overall = "review"
    else:
        overall = "ready"
    return {
        "schema_version": config["schema_version"],
        "eligibility": eligibility,
        "parseability": parsing,
        "match": match,
        "human_quality": human_quality,
        "truthfulness": truthfulness,
        "overall_status": overall,
    }
