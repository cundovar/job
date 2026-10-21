"""Assemblage du CV rédigé par un agent et fusion des verdicts (véracité, jugement, corrections).

Extrait de cv_generator/ai_agents.py, sans changement de comportement.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List

from cv_generator.cv_creator import build_structural_shell
from cv_generator.cv_truth_validator import validate_cv_content
from cv_generator import rules as candidate_rules
from cv_generator.utils import compact_items, normalize, period_to_text
from .ai_client import AgentResult, CVAgentError
from .ai_plan import _agent_run, _as_string_list, _candidate_title, _clip, _filter_skills_whitelist, _int_score


def to_writer_schema(content: Dict[str, Any]) -> Dict[str, Any]:
    """Déballe un CV assemblé vers le schéma que les agents rédigent.

    Le réviseur doit rendre la forme du rédacteur. Lui montrer la structure
    assemblée — imbriquée sous `cv`, puces en texte, provenance dans un tableau
    parallèle — l'invitait à recopier cette forme-là : sa réponse arrivait alors
    sous `{"cv": ...}` et le contrat sautait. Le déballage préserve les sources
    de chaque puce, qui sont ce que le réviseur doit impérativement conserver.
    """
    cv = content.get("cv", content) if isinstance(content, dict) else {}
    experiences = []
    for item in cv.get("experiences", []) or []:
        if not isinstance(item, dict):
            continue
        bullets = item.get("bullets", []) or []
        sources = item.get("bullet_sources", []) or []
        entry: Dict[str, Any] = {
            "id": item.get("id"),
            "bullets": [
                {
                    "text": str(text),
                    "sources": list(sources[index]) if index < len(sources) else [],
                }
                for index, text in enumerate(bullets)
            ],
        }
        if item.get("source_experience_ids"):
            entry["source_experience_ids"] = list(item["source_experience_ids"])
        experiences.append(entry)
    return {
        "title": cv.get("title", ""),
        "profile": cv.get("profile", ""),
        "skills": [
            {"title": section.get("title", ""), "items": list(section.get("items", []) or [])}
            for section in cv.get("skills", []) or []
            if isinstance(section, dict)
        ],
        "experiences": experiences,
        "projects": [
            {
                "id": project.get("id"),
                "description": project.get("description", ""),
                "technologies": list(project.get("technologies", []) or []),
            }
            for project in cv.get("projects", []) or []
            if isinstance(project, dict)
        ],
        "education": [
            item.get("title") if isinstance(item, dict) else item
            for item in cv.get("education", []) or []
        ],
    }


def _filter_education_by_variant(
    proposed: Any,
    education_catalog: Dict[str, Dict[str, Any]],
    variant_id: str,
    master: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """N'affiche qu'un diplôme autorisé pour la variante retenue.

    Décision candidate portée par `present_on_variants` (liste d'ids de
    variantes) dans `person.education` : un diplôme peut être réservé à
    certaines familles de CV — deug et diplômes du développement sur un CV de
    développeur, le complet sur un CV de formateur. Sans champ, aucune
    restriction. Un intitulé inconnu du catalogue passe tel quel : le
    validateur le signale, Python ne l'invente pas.
    """
    education: List[Dict[str, Any]] = []
    for item in proposed or []:
        title = item.get("title") if isinstance(item, dict) else item
        entry = education_catalog.get(normalize(title))
        if entry is not None:
            allowed = entry.get("present_on_variants")
            if allowed and variant_id not in allowed:
                continue
            education.append(candidate_rules.displayed_education_entry(entry, master or {}, variant_id))
        else:
            education.append({"title": str(title)})
    return education


def _assemble_cv_content(
    proposed: Dict[str, Any],
    job: Dict[str, Any],
    master: Dict[str, Any],
    plan: Dict[str, Any],
    run: AgentResult,
    agent_name: str,
) -> Dict[str, Any]:
    """Assemble le CV rendu à partir du seul contenu écrit par l'agent.

    Python recopie ce qui appartient à la source de vérité — intitulés,
    organisations, périodes, liens — et n'ajoute rien d'autre. La sélection,
    l'ordre, le regroupement et le texte restent ceux de l'agent. Ce qui ne
    tient pas le contrat devient une erreur rendue au réviseur, pas une
    correction silencieuse.
    """
    constraints = master.get("layout_constraints", {})
    catalog = master.get("experience_catalog", {})
    groups = master.get("experience_groups", {})

    raw_experiences = proposed.get("experiences")
    if not isinstance(raw_experiences, list) or not raw_experiences:
        raise CVAgentError(
            f"L'agent {agent_name} n'a retourné aucune expérience. La sélection est "
            "un choix éditorial : Python n'en fabrique pas."
        )

    experiences: List[Dict[str, Any]] = []
    grounding: List[Dict[str, Any]] = []
    for item in raw_experiences:
        if not isinstance(item, dict):
            continue
        exp_id = str(item.get("id") or "")
        member_ids = [
            str(member)
            for member in (item.get("source_experience_ids") or [])
            if isinstance(member, (str, int))
        ]
        source = catalog.get(exp_id)
        group = groups.get(exp_id)
        if source is None and group is None:
            # L'identifiant est refusé, pas remplacé : le validateur le signalera.
            experiences.append({"id": exp_id, "bullets": [], "bullet_sources": []})
            continue

        bullets: List[str] = []
        bullet_sources: List[List[str]] = []
        for raw_bullet in item.get("bullets", []) or []:
            if isinstance(raw_bullet, dict):
                text = re.sub(r"\s+", " ", str(raw_bullet.get("text") or "")).strip()
                sources = raw_bullet.get("sources")
                if isinstance(sources, str):
                    sources = [sources]
                if not isinstance(sources, list):
                    legacy = raw_bullet.get(
                        "source_highlight_indexes", raw_bullet.get("source_highlight_index")
                    )
                    if isinstance(legacy, int):
                        legacy = [legacy]
                    sources = (
                        [f"{exp_id}:{index}" for index in legacy if isinstance(index, int)]
                        if isinstance(legacy, list)
                        else []
                    )
            else:
                text = re.sub(r"\s+", " ", str(raw_bullet or "")).strip()
                sources = []
            if not text:
                continue
            bullets.append(text)
            bullet_sources.append([str(reference).strip() for reference in sources])
            grounding.append(
                {"experience_id": exp_id, "bullet": text, "sources": bullet_sources[-1]}
            )

        if group is not None:
            organizations = [
                str(catalog[member].get("organization") or "")
                for member in member_ids
                if member in catalog
            ]
            links = candidate_rules.shown_links(
                link for member in member_ids for link in catalog.get(member, {}).get("links", [])
            )
            entry = {
                "id": exp_id,
                "source_experience_ids": member_ids,
                "selection_role": "core",
                "organization": " · ".join(
                    organization for organization in dict.fromkeys(organizations) if organization
                ),
                "title": _candidate_title(item, master) or group.get("title", "Missions et projets professionnels"),
                "period": period_to_text(group.get("period")),
                "bullets": bullets,
                "bullet_sources": bullet_sources,
                "links": links[:2],
            }
        else:
            entry = {
                "id": exp_id,
                "selection_role": source.get("cv_role", "core"),
                "organization": source.get("organization", ""),
                "title": _candidate_title(item, master) or source.get("title", ""),
                "period": period_to_text(source.get("period")),
                "bullets": bullets,
                "bullet_sources": bullet_sources,
                "links": candidate_rules.shown_links(source.get("links"))[:2],
            }
        experiences.append(entry)

    projects: List[Dict[str, Any]] = []
    for item in proposed.get("projects") or []:
        if not isinstance(item, dict):
            continue
        project_id = str(item.get("id") or "")
        source = master.get("project_catalog", {}).get(project_id)
        if source is None:
            projects.append({"id": project_id, "title": "", "description": "", "technologies": []})
            continue
        requested = item.get("technologies")
        projects.append(
            {
                "id": project_id,
                "title": source.get("title", ""),
                "year": source.get("year"),
                "description": re.sub(
                    r"\s+", " ", str(item.get("description") or source.get("description", ""))
                ).strip(),
                "technologies": (
                    [str(technology) for technology in requested]
                    if isinstance(requested, list)
                    else source.get("technologies", [])
                ),
                "links": candidate_rules.shown_links(source.get("links"))[:2],
            }
        )

    person = master.get("person", {})
    variant_id = str(plan.get("selected_base_variant") or "")
    education_catalog = {
        normalize(entry.get("title")): entry
        for entry in person.get("education", [])
        if isinstance(entry, dict) and normalize(entry.get("title"))
    }
    education = _filter_education_by_variant(
        proposed.get("education"), education_catalog, variant_id, master
    )

    cv = {
        "title": re.sub(r"\s+", " ", str(proposed.get("title") or "")).strip(),
        "profile": re.sub(r"\s+", " ", str(proposed.get("profile") or "")).strip(),
        "section_order": plan.get(
            "section_order", ["profile", "skills", "experiences", "projects", "education"]
        ),
        "contact": build_structural_shell(master, variant_id)["contact"],
        "location": person.get("location", ""),
        "skills": _filter_skills_whitelist(proposed.get("skills"), master),
        "experiences": experiences,
        "projects": projects,
        "education": education,
        "languages": person.get("languages", []),
    }

    content = {
        "agent": agent_name,
        "agent_run": _agent_run(run),
        "generated_for": {
            "job_title": job.get("title"),
            "company": job.get("company"),
            "source_url": job.get("url"),
        },
        "base_variant": plan.get("selected_base_variant"),
        "cv": cv,
        "grounding": {"experience_bullets": grounding},
    }
    validation = validate_cv_content(content, master, plan)
    content["python_validation"] = {
        "ok": validation["ok"],
        "truthful": validation["truthful"],
        "issues": validation["issues"],
    }
    return content


SOURCE_GAP_CODE = "SOURCE_GAP"


def _is_source_gap(problem: Dict[str, Any]) -> bool:
    return str(problem.get("code") or "").strip().upper() == SOURCE_GAP_CODE


def _normalize_problems(value: Any) -> List[Dict[str, str]]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity") or "medium").lower()
        if severity not in {"high", "medium", "low"}:
            severity = "medium"
        if str(item.get("code") or "").strip().upper() == SOURCE_GAP_CODE:
            # Un écart de source n'est réparable par aucun agent : il ne peut
            # pas porter une sévérité qui forcerait une révision.
            severity = "low"
        problem = _clip(item.get("problem"), 360)
        if not problem:
            continue
        result.append(
            {
                "code": _clip(item.get("code"), 80),
                "severity": severity,
                "section": _clip(item.get("section"), 80, "general"),
                "problem": problem,
                "suggested_fix": _clip(item.get("suggested_fix"), 360),
            }
        )
    return result[:20]


def _normalize_evidence_coverage(value: Any, master: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    allowed_pillars = {
        "pedagogy",
        "technical_delivery",
        "ai_practice",
        "public_proof",
        "human_group_facilitation",
    }
    allowed_statuses = {"covered", "partial", "missing", "not_applicable"}
    experience_ids = set(master.get("experience_catalog", {}))
    project_ids = set(master.get("project_catalog", {}))
    result: List[Dict[str, Any]] = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        pillar = str(item.get("pillar") or "").strip().lower()
        if pillar not in allowed_pillars or pillar in seen:
            continue
        status = str(item.get("status") or "missing").strip().lower()
        if status not in allowed_statuses:
            status = "missing"
        result.append(
            {
                "pillar": pillar,
                "status": status,
                "experience_ids": [
                    exp_id
                    for exp_id in _as_string_list(item.get("experience_ids"), 8)
                    if exp_id in experience_ids
                ],
                "project_ids": [
                    project_id
                    for project_id in _as_string_list(item.get("project_ids"), 8)
                    if project_id in project_ids
                ],
                "gap": _clip(item.get("gap"), 300),
            }
        )
        seen.add(pillar)
    return result


def _path_segments(path: str) -> tuple[str, ...]:
    """« experiences[0].bullets[1] » → ('experiences', '0', 'bullets', '1').

    La comparaison passe par les segments plutôt que par un préfixe texte :
    « [1] » ne doit jamais matcher « [10] ».
    """
    return tuple(
        piece for piece in str(path).replace("[", ".").replace("]", "").split(".") if piece
    )


def _claim_affected(claim_path: str, changed_paths: List[str]) -> bool:
    """Un claim est touché si son chemin contient — ou est contenu dans — un chemin modifié."""
    segments = _path_segments(claim_path)
    for changed in changed_paths:
        other = _path_segments(changed)
        if other[: len(segments)] == segments or segments[: len(other)] == other:
            return True
    return False


def _cv_diff_paths(previous: Any, current: Any, prefix: str = "") -> List[str]:
    """Chemins (convention des claims) où `current` diffère de `previous`.

    Comparaison purement mécanique, donc du ressort de Python : elle ne dit
    rien du sens, elle dit seulement où le réviseur est intervenu.
    """
    if type(previous) is not type(current):
        return [prefix or "<racine>"]
    if isinstance(previous, dict):
        paths: List[str] = []
        for key in sorted(set(previous) | set(current)):
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            if key not in previous or key not in current:
                paths.append(child_prefix)
            else:
                paths.extend(_cv_diff_paths(previous[key], current[key], child_prefix))
        return paths
    if isinstance(previous, list):
        if len(previous) != len(current):
            return [prefix or "<racine>"]
        paths = []
        for index, (old_item, new_item) in enumerate(zip(previous, current)):
            paths.extend(_cv_diff_paths(old_item, new_item, f"{prefix}[{index}]"))
        return paths
    return [] if previous == current else [prefix or "<racine>"]


#: Blocs que Python recopie mot pour mot depuis le profil maître. Le
#: vérificateur juge le texte rédigé, pas le travail de recopie : une
#: coordonnée qu'il déclare « sans preuve » bloquerait un CV que personne n'a
#: inventé, et le blocage tomberait au hasard d'un tour à l'autre.
_PYTHON_OWNED_PATHS = ("contact",)


def _is_python_owned(path: Any) -> bool:
    head = str(path or "").split(".")[0].split("[")[0].strip()
    return head in _PYTHON_OWNED_PATHS


def _merge_truth_check(
    proposed: Dict[str, Any],
    validation: Dict[str, Any],
    run: AgentResult,
    previous_claims: List[Dict[str, Any]] | None = None,
    changed_paths: List[str] | None = None,
) -> Dict[str, Any]:
    """Fusionne le contrôle Python et le jugement de l'agent vérificateur.

    Python voit les références introuvables, l'agent voit l'écart de sens entre
    une preuve et sa reformulation. Les deux bloquent, aucun ne réécrit.
    """
    claims: List[Dict[str, Any]] = []
    for item in proposed.get("claims") or []:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").strip().lower()
        if status not in {"supported", "unsupported"}:
            status = "unsupported"
        path = _clip(item.get("path"), 120)
        if not path:
            continue
        claims.append(
            {
                "path": path,
                "source_refs": _as_string_list(item.get("source_refs"), 8),
                "status": status,
                "reason": _clip(item.get("reason"), 300),
            }
        )
    targeted: Dict[str, Any] | None = None
    if previous_claims is not None:
        # Véracité ciblée : les chemins intacts conservent le verdict rendu au
        # tour précédent — un texte identique ne peut pas changer de sens.
        # Un claim que l'agent rendrait sur un chemin intact est ignoré : le
        # statut précédent fait foi, il porte sur exactement le même texte.
        paths = changed_paths or []
        kept = [
            item
            for item in previous_claims
            if isinstance(item, dict) and not _claim_affected(str(item.get("path") or ""), paths)
        ]
        kept_paths = {item.get("path") for item in kept}
        claims = kept + [item for item in claims if item["path"] not in kept_paths]
        targeted = {
            "mode": "reused" if not paths else "targeted",
            "changed_paths": paths,
            "reused_claims": len(kept),
        }
    unsupported = [item for item in claims if item["status"] == "unsupported"]
    # Écartés du verdict, jamais effacés : le constat reste lisible dans le
    # fichier, il ne décide simplement pas de la publication.
    ignored_claims = [item for item in unsupported if _is_python_owned(item["path"])]
    unsupported = [item for item in unsupported if not _is_python_owned(item["path"])]
    issues = list(validation["truth_issues"])
    for item in unsupported:
        issues.append(
            {
                "code": "CLAIM_NOT_SUPPORTED_BY_SOURCE",
                "kind": "truth",
                "path": item["path"],
                "detail": item["reason"] or "Reformulation non soutenue par la preuve citée.",
                "reference": ", ".join(item["source_refs"]) or None,
            }
        )
    merged = {
        "agent": "cv_truth_checker_ai",
        "agent_run": _agent_run(run),
        "verdict": "refused" if issues else "accepted",
        "claims": claims,
        "unsupported_count": len(unsupported),
        "ignored_claims": ignored_claims,
        "truth_issues": issues,
        "format_issues": validation["format_issues"],
        # Une source incomplète n'entre pas dans le contrat de correction : le
        # réviseur n'a rien à y réparer, elle se transporte jusqu'au verdict.
        "source_issues": validation.get("source_issues", []),
        "python_validation": {
            "ok": validation["ok"],
            "truthful": validation["truthful"],
            "issues": validation["issues"],
        },
    }
    if targeted is not None:
        merged["targeted"] = targeted
    return merged


def _merge_review(
    proposed: Dict[str, Any],
    deterministic: Dict[str, Any],
    run: AgentResult,
    master: Dict[str, Any],
) -> Dict[str, Any]:
    problems = _normalize_problems(proposed.get("problems"))
    # Ce que le juge IA a lui-même relevé, avant fusion avec les signalements
    # Python : c'est sur cette seule liste qu'on contrôle la cohérence du verdict.
    ai_reported_high = any(
        item.get("severity") == "high" and not _is_source_gap(item) for item in problems
    )
    known = {(item["section"], item["problem"]) for item in problems}
    technical_sections = {"truthfulness", "header", "profile", "skills", "experiences", "evidence"}
    technical_problems = [
        item
        for item in _normalize_problems(deterministic.get("problems"))
        if item.get("section") in technical_sections
    ]
    for item in technical_problems:
        key = (item["section"], item["problem"])
        if key not in known:
            problems.append(item)
            known.add(key)
    missing = _as_string_list(proposed.get("missing_keywords"), 20)
    forbidden = compact_items(
        [
            *_as_string_list(proposed.get("forbidden_claims_found"), 20),
            *_as_string_list(deterministic.get("forbidden_claims_found"), 20),
        ],
        limit=20,
    )
    quality_score = _int_score(proposed.get("quality_score"), _int_score(deterministic.get("quality_score"), 0))
    ats_score = _int_score(proposed.get("ats_score"), _int_score(deterministic.get("ats_score"), 0))
    status = str(proposed.get("status") or "").strip().lower()
    if status not in {"validated", "needs_minor_revision", "needs_revision"}:
        status = "needs_revision" if problems else "validated"
    # Python impose une révision sur une erreur de vérité, jamais sur un
    # jugement de pertinence : une compétence insuffisamment prouvée est un
    # signalement remis au juge IA, pas un veto déterministe.
    source_gaps = compact_items(
        [
            *_as_string_list(proposed.get("source_gaps"), 20),
            *[item["problem"] for item in problems if _is_source_gap(item)],
        ],
        limit=20,
    )
    repairable = [item for item in problems if not _is_source_gap(item)]
    if (
        status != "validated"
        and not repairable
        and not deterministic.get("format_issues")
        and not deterministic.get("truth_blocking")
        and not forbidden
    ):
        # Seuls des écarts de source restent : une révision ne changerait rien
        # (elle finirait en no_progress). Le CV est validé, les écarts sont
        # transmis à la lettre et à l'entretien via source_gaps.
        status = "validated"
    if deterministic.get("truth_blocking") or forbidden:
        status = "needs_revision"
    elif ai_reported_high:
        # Un juge qui signale un problème grave et conclut « validated » se
        # contredit : Python refuse le verdict, pas la pertinence.
        status = "needs_revision"
    elif deterministic.get("format_issues") and status == "validated":
        # Un dépassement de gabarit interdit l'export : il justifie une passe de
        # correction, à la différence d'un simple signalement de pertinence.
        status = "needs_minor_revision"
    return {
        "agent": "cv_quality_checker_ai",
        "agent_run": _agent_run(run),
        "quality_score": quality_score,
        "ats_score": ats_score,
        "status": status,
        "strengths": _as_string_list(proposed.get("strengths"), 10),
        "problems": problems,
        "problem_codes": sorted({item.get("code") for item in problems if item.get("code")}),
        "missing_keywords": missing,
        "source_gaps": source_gaps,
        "overrepresented_keywords": _as_string_list(proposed.get("overrepresented_keywords"), 20),
        "forbidden_claims_found": forbidden,
        "evidence_coverage": _normalize_evidence_coverage(
            proposed.get("evidence_coverage"),
            master,
        ),
        "verdict": _clip(
            proposed.get("verdict"),
            500,
            "Validé" if status == "validated" else "Corriger puis relire",
        ),
        "python_guardrail_review": deterministic,
    }


def build_correction_contract(
    review: Dict[str, Any],
    truth_check: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """Les corrections à appliquer, vérité d'abord, en une seule liste.

    Le réviseur reçoit les trois origines — vérité, gabarit, pertinence — dans
    un format unique, pour ne pas avoir à deviner laquelle bloque la
    publication.
    """
    corrections: List[Dict[str, Any]] = []
    truth = truth_check or {}
    for issue in truth.get("truth_issues", []):
        corrections.append(
            {
                "origin": "truth",
                "blocking": True,
                "code": issue.get("code"),
                "location": issue.get("path"),
                "problem": issue.get("detail"),
                "reference": issue.get("reference"),
            }
        )
    for issue in truth.get("format_issues", []):
        corrections.append(
            {
                "origin": "format",
                "blocking": True,
                "code": issue.get("code"),
                "location": issue.get("path"),
                "problem": issue.get("detail"),
                "reference": issue.get("reference"),
            }
        )
    for problem in review.get("problems", []):
        if _is_source_gap(problem):
            # Rien à corriger dans le CV : l'écart est assumé et remonté via
            # review["source_gaps"] pour la lettre de motivation.
            continue
        corrections.append(
            {
                "origin": "relevance",
                "blocking": False,
                "code": problem.get("code"),
                "location": problem.get("section"),
                "problem": problem.get("problem"),
                "suggested_fix": problem.get("suggested_fix"),
            }
        )
    return corrections


def correction_fingerprint(
    content: Dict[str, Any],
    corrections: List[Dict[str, Any]],
) -> str:
    """Empreinte du couple contenu/problèmes, pour détecter une boucle stagnante."""
    payload = json.dumps(
        {
            "cv": content.get("cv", {}),
            "issues": sorted(
                f"{item.get('origin')}:{item.get('code')}:{item.get('location')}"
                for item in corrections
            ),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
