from __future__ import annotations

from typing import Any, Dict, List

from .cv_truth_validator import TRUTH, validate_cv_content
from .utils import normalize
from .layout import title_requires_wrap


def _collect_cv_text(draft: Dict[str, Any]) -> str:
    cv = draft.get("cv", {})
    parts: List[str] = [cv.get("title", ""), cv.get("profile", "")]
    for section in cv.get("skills", []):
        parts.append(section.get("title", ""))
        parts.extend(section.get("items", []))
    for exp in cv.get("experiences", []):
        parts.extend([exp.get("title", ""), exp.get("organization", "")])
        parts.extend(exp.get("bullets", []))
    for project in cv.get("projects", []):
        parts.extend([project.get("title", ""), project.get("description", "")])
    return normalize(" ".join(parts))


#: Une erreur de vérité bloque; une erreur de gabarit se corrige en révision.
_SEVERITY_BY_KIND = {TRUTH: "high", "format": "medium"}

#: Rattachement des codes du validateur aux sections lues par le juge IA.
_SECTION_BY_CODE = {
    "PROFILE_TOO_LONG": "profile",
    "TOO_MANY_SKILLS": "skills",
    "TOO_MANY_SKILL_SECTIONS": "skills",
    "UNKNOWN_SKILL": "skills",
    "EXCLUDED_SKILL": "skills",
    "FORBIDDEN_CLAIM": "truthfulness",
    "UNKNOWN_SECTION": "header",
}


def _section_for(issue: Dict[str, Any]) -> str:
    code = str(issue.get("code") or "")
    if code in _SECTION_BY_CODE:
        return _SECTION_BY_CODE[code]
    path = str(issue.get("path") or "")
    for section in ("experiences", "projects", "education", "skills", "profile"):
        if path.startswith(section):
            return section
    return "truthfulness" if issue.get("kind") == TRUTH else "general"


def review_cv(job: Dict[str, Any], master: Dict[str, Any], plan: Dict[str, Any], draft: Dict[str, Any]) -> Dict[str, Any]:
    """Contrôle Python non modificatif, transmis au juge IA comme signalement.

    La vérité et le gabarit viennent de ``cv_truth_validator`` : ce module ne
    les recalcule plus. Il n'ajoute ici que les heuristiques de couverture
    (mots-clés, preuves visibles, positionnement) qui aident le juge sans
    jamais décider à sa place de la pertinence éditoriale.
    """
    cv = draft.get("cv", {})
    validation = validate_cv_content(draft, master, plan)
    cv_text = _collect_cv_text(draft)
    problems = []
    missing = []
    for keyword in plan.get("priority_keywords", [])[:10]:
        if normalize(keyword) not in cv_text:
            missing.append(keyword)
    if missing:
        problems.append({
            "severity": "medium",
            "section": "keywords",
            "problem": "Certains mots-clés prioritaires de l'annonce ne sont pas visibles dans le CV.",
            "suggested_fix": "Ajouter les mots-clés manquants quand ils sont vrais dans le profil.",
        })
    visible_project_ids = {item.get("id") for item in cv.get("projects", [])}
    visible_experience_ids = set()
    for item in cv.get("experiences", []):
        visible_experience_ids.add(item.get("id"))
        visible_experience_ids.update(item.get("source_experience_ids", []))
    evidence_by_requirement = {}
    for match in plan.get("evidence_matches", []):
        requirement = str(match.get("requirement") or "compétence")
        target = evidence_by_requirement.setdefault(requirement, {"project_ids": set(), "experience_ids": set()})
        target["project_ids"].update(match.get("project_ids", []))
        target["experience_ids"].update(match.get("experience_ids", []))
    for requirement, evidence in evidence_by_requirement.items():
        project_ids = evidence["project_ids"]
        experience_ids = evidence["experience_ids"]
        if (project_ids or experience_ids) and not (
            project_ids & visible_project_ids or experience_ids & visible_experience_ids
        ):
            problems.append({
                "code": "SKILL_WITHOUT_EVIDENCE",
                "severity": "high",
                "section": "evidence",
                "problem": f"L'exigence importante « {requirement} » ne possède aucune preuve visible dans le CV.",
                "suggested_fix": "Ajouter un projet ou une expérience sourcée correspondant à cette exigence.",
            })
    for issue in validation["issues"]:
        problems.append(
            {
                "code": issue["code"],
                "severity": _SEVERITY_BY_KIND.get(issue["kind"], "medium"),
                "section": _section_for(issue),
                "problem": issue["detail"],
                "suggested_fix": (
                    "Corriger en s'appuyant uniquement sur le profil maître, "
                    "ou retirer l'affirmation."
                ),
            }
        )
    forbidden_hits = [
        str(issue.get("reference") or "")
        for issue in validation["truth_issues"]
        if issue["code"] == "FORBIDDEN_CLAIM"
    ]
    if title_requires_wrap(str(cv.get("title") or "")):
        problems.append({
            "severity": "medium",
            "section": "header",
            "problem": "Le sous-titre est trop large sur une ligne et risque de dépasser la colonne imprimable.",
            "suggested_fix": "Le couper en deux lignes avant l'export.",
        })
    base_variant = draft.get("base_variant")
    if base_variant in {"webmaster", "wordpress", "formateur_generaliste", "accessibilite"} and "full stack" in cv_text:
        problems.append({
            "severity": "medium",
            "section": "positioning",
            "problem": "Le CV reste trop orienté full-stack pour cette variante.",
            "suggested_fix": "Remplacer l'accroche par un positionnement webmaster/formateur/accessibilité selon l'annonce.",
        })
    quality_score = max(0, 100 - len(problems) * 9 - len(missing) * 2 - len(forbidden_hits) * 12)
    ats_score = max(0, 100 - len(missing) * 6)
    has_high_severity = any(item.get("severity") == "high" for item in problems)
    status = "validated" if quality_score >= 85 and not forbidden_hits else "needs_revision"
    if has_high_severity:
        status = "needs_revision"
    elif problems and quality_score >= 85:
        status = "needs_minor_revision"
    return {
        "agent": "cv_quality_checker",
        # Seule une erreur de vérité autorise Python à imposer une révision.
        # Les mots-clés manquants et les preuves jugées insuffisantes sont des
        # signalements remis au juge IA, qui reste maître de la pertinence.
        "truth_blocking": not validation["truthful"],
        "truth_issues": validation["truth_issues"],
        "format_issues": validation["format_issues"],
        "quality_score": quality_score,
        "ats_score": ats_score,
        "status": status,
        "strengths": [
            f"Variante de base choisie : {base_variant}.",
            "CV généré depuis le catalogue source sans ajout libre.",
        ],
        "problems": problems,
        "problem_codes": sorted({item.get("code") for item in problems if item.get("code")}),
        "missing_keywords": missing,
        "overrepresented_keywords": [],
        "forbidden_claims_found": forbidden_hits,
        "verdict": "Validé" if status == "validated" else "Corriger puis relire",
    }
