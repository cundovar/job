from __future__ import annotations

from typing import Any, Dict, List

from .utils import normalize


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


def review_cv(job: Dict[str, Any], master: Dict[str, Any], plan: Dict[str, Any], draft: Dict[str, Any]) -> Dict[str, Any]:
    constraints = master.get("layout_constraints", {})
    cv = draft.get("cv", {})
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
    profile = cv.get("profile", "")
    if len(profile) > int(constraints.get("max_profile_chars", 420)):
        problems.append({"severity": "medium", "section": "profile", "problem": "Résumé trop long pour Canva.", "suggested_fix": "Réduire le résumé à deux phrases."})
    max_bullets = int(constraints.get("max_bullets_per_experience", 3))
    max_bullet_chars = int(constraints.get("max_bullet_chars", 145))
    for exp in cv.get("experiences", []):
        if len(exp.get("bullets", [])) > max_bullets:
            problems.append({"severity": "low", "section": "experiences", "problem": f"Trop de bullets pour {exp.get('organization')}", "suggested_fix": "Garder les 3 bullets les plus pertinents."})
        for bullet in exp.get("bullets", []):
            if len(bullet) > max_bullet_chars:
                problems.append({"severity": "low", "section": "experiences", "problem": "Bullet trop long.", "suggested_fix": "Raccourcir à environ 145 caractères."})
    forbidden_hits = []
    for claim in master.get("forbidden_claims", []):
        if normalize(claim) in cv_text:
            forbidden_hits.append(claim)
    if forbidden_hits:
        problems.append({
            "severity": "high",
            "section": "truthfulness",
            "problem": "Formulation interdite ou trop survendue détectée.",
            "suggested_fix": "Supprimer ou reformuler les affirmations interdites.",
        })
    base_variant = draft.get("base_variant")
    if base_variant in {"webmaster", "wordpress", "formateur_developpement_web", "formateur_ia", "accessibilite"} and "full stack" in cv_text:
        problems.append({
            "severity": "medium",
            "section": "positioning",
            "problem": "Le CV reste trop orienté full-stack pour cette variante.",
            "suggested_fix": "Remplacer l'accroche par un positionnement webmaster/formateur/accessibilité selon l'annonce.",
        })
    quality_score = max(0, 100 - len(problems) * 9 - len(missing) * 2 - len(forbidden_hits) * 12)
    ats_score = max(0, 100 - len(missing) * 6)
    status = "validated" if quality_score >= 85 and not forbidden_hits else "needs_revision"
    if problems and quality_score >= 85:
        status = "needs_minor_revision"
    return {
        "agent": "cv_quality_checker",
        "quality_score": quality_score,
        "ats_score": ats_score,
        "status": status,
        "strengths": [
            f"Variante de base choisie : {base_variant}.",
            "CV généré depuis le catalogue source sans ajout libre.",
        ],
        "problems": problems,
        "missing_keywords": missing,
        "overrepresented_keywords": [],
        "forbidden_claims_found": forbidden_hits,
        "verdict": "Validé" if status == "validated" else "Corriger puis relire",
    }
