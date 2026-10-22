"""Plan de l'agent analyste : contexte envoyé aux agents et validation du plan par Python.

Extrait de cv_generator/ai_agents.py, sans changement de comportement.
"""

from __future__ import annotations

import re
import time
from dataclasses import replace as dataclass_replace
from typing import Any, Dict, Iterable, List

from cv_generator.cv_truth_validator import ALLOWED_SECTIONS
from cv_generator.cv_truth_validator import candidate_excludes
from cv_generator import rules as candidate_rules
from cv_generator.declared_experiences import declared_id_map, validate_declared, with_declared_experiences
from cv_generator.utils import compact_items, flatten_skills, normalize
from .ai_client import AgentClient, AgentResult, CVAgentError


def _agent_call(
    client: AgentClient,
    agent_name: str,
    system_prompt: str,
    payload: Dict[str, Any],
) -> AgentResult:
    started = time.monotonic()
    raw = client.complete_json(
        agent_name=agent_name,
        system_prompt=system_prompt,
        payload=payload,
    )
    duration = time.monotonic() - started
    if isinstance(raw, AgentResult):
        return dataclass_replace(raw, duration_seconds=round(duration, 1))
    if isinstance(raw, dict):
        return AgentResult(raw, "injected", "test-or-custom", round(duration, 1))
    raise CVAgentError(f"Réponse invalide de l'agent {agent_name}")


def visible_experience_catalog(master: Dict[str, Any]) -> Dict[str, Any]:
    """Le catalogue sans les expériences retirées du parcours.

    `retired` est une décision du candidat, pas un jugement éditorial : une
    expérience retirée n'est pas proposée aux agents, qui ne peuvent donc pas
    la choisir. Elle reste dans le profil maître — l'effacer perdrait un
    morceau de parcours réel, et le validateur doit encore savoir la
    reconnaître si un ancien CV la cite.
    """
    catalog = master.get("experience_catalog", {})
    return {
        identifier: entry
        for identifier, entry in catalog.items()
        if not (isinstance(entry, dict) and entry.get("retired") is True)
    }


def _truth_context(master: Dict[str, Any], role: str) -> Dict[str, Any]:
    """Return only the source-of-truth fields useful to a given AI role.

    The full master profile is intentionally not sent to every agent: repeated
    irrelevant sections increase prompt size and latency without improving the
    grounded Python guardrails that still validate the result afterwards.
    """
    person = master.get("person", {})
    common = {
        "person": {
            "display_name": person.get("display_name"),
            # Pas de coordonnées : Python les recopie lui-même dans le CV à
            # l'assemblage, et aucun CV envoyé aux agents ne les porte
            # (without_contact). Téléphone et email ne quittent pas le serveur.
            "location": person.get("location"),
            "languages": person.get("languages", []),
            "education": person.get("education", []),
            "eligibility": person.get("eligibility", {}),
        },
        "skills_confidence": master.get("skills_confidence", {}),
        "experience_catalog": visible_experience_catalog(master),
        "project_catalog": master.get("project_catalog", {}),
        "evidence_catalog": master.get("evidence_catalog", {}),
        "experience_groups": master.get("experience_groups", {}),
        "layout_constraints": master.get("layout_constraints", {}),
        # Le titre du CV est choisi parmi ces variants par l'analyste. Sans eux,
        # le vérificateur refusait un titre pourtant autorisé par la source :
        # le positionnement est la référence légitime pour juger un titre.
        "title_variants": (master.get("positioning", {}) or {}).get("title_variants", {}),
        # Consignes du candidat : source de vérité supérieure (règle Cundo 21/10/2026),
        # citables par les puces sous « consignes_candidat:N ».
        "declarations_candidat": list(enumerate(master.get("candidate_statements", []) or [])),
    }

    if role == "analyzer":
        common.update({
            "positioning": master.get("positioning", {}),
            "cv_variants": master.get("cv_variants", []),
            "adaptation_rules": master.get("adaptation_rules", {}),
        })
    elif role in {"creator", "reviser"}:
        common.update({
            "forbidden_claims": master.get("forbidden_claims", []),
            "adaptation_rules": master.get("adaptation_rules", {}),
        })
    elif role == "reviewer":
        common.update({
            "forbidden_claims": master.get("forbidden_claims", []),
            "adaptation_rules": master.get("adaptation_rules", {}),
        })
    return common


def _agent_run(result: AgentResult) -> Dict[str, Any]:
    return {
        "provider": result.provider,
        "model": result.model,
        "duration_seconds": result.duration_seconds,
    }


def _clip(value: Any, limit: int, fallback: str = "") -> str:
    text = re.sub(r"\s+", " ", str(value or fallback)).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip(" ,;:") + "…"


def _as_string_list(value: Any, limit: int = 20) -> List[str]:
    if not isinstance(value, list):
        return []
    return compact_items((str(item) for item in value), limit=limit)


def _candidate_instructions(job: Dict[str, Any]) -> str:
    return _clip(job.get("candidate_instructions"), 2000)


def _announcement_context(job: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in job.items() if key != "candidate_instructions"}


def _int_score(value: Any, fallback: int) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return fallback


def _allowed_skills(master: Dict[str, Any]) -> Dict[str, str]:
    skills: List[str] = list(master.get("skills_confidence", {}).keys())
    for variant in master.get("cv_variants", []):
        skills.extend(flatten_skills(variant.get("skills", {})))
    return {normalize(skill): str(skill) for skill in skills if normalize(skill)}


def _sanitize_skill_mapping(
    value: Any,
    master: Dict[str, Any],
    variant_id: str = "",
) -> Dict[str, List[str]]:
    if not isinstance(value, dict):
        return {}
    allowed = _allowed_skills(master)
    excluded = {
        normalize(skill)
        for skill in (
            master.get("adaptation_rules", {})
            .get("excluded_skills_by_variant", {})
            .get(variant_id, [])
        )
    }
    result: Dict[str, List[str]] = {}
    used = 0
    max_sections = int(master.get("layout_constraints", {}).get("max_skill_sections", 4))
    max_items = int(master.get("layout_constraints", {}).get("max_skill_items_total", 10))
    for section, items in value.items():
        if not isinstance(items, list) or len(result) >= max_sections or used >= max_items:
            continue
        picked: List[str] = []
        for item in items:
            canonical = allowed.get(normalize(item))
            if canonical and normalize(canonical) not in excluded and canonical not in picked:
                picked.append(canonical)
            if len(picked) >= min(8, max_items - used):
                break
        if picked:
            result[_clip(section, 60, "Compétences")] = picked
            used += len(picked)
    return result


def _filter_skills_whitelist(
    skills: Any,
    master: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """N'autorise en section compétences que les libellés du profil maître.

    Même contrat que `_sanitize_skill_mapping` sur le plan, appliqué au contenu
    final : chaque libellé est ramené à sa forme canonique ou retiré. Sans ce
    filtre au point d'assemblage, le réviseur (patch ou réécriture complète)
    réintroduisait un vocabulaire d'offre que la liste blanche ne porte pas —
    le contrôle qualité le refusait trois tours plus tard (UNKNOWN_SKILL) et
    le CV finissait bloqué (cas La Goutte d'Or, 23/09/2026).
    """
    allowed = _allowed_skills(master)
    sections: List[Dict[str, Any]] = []
    if not isinstance(skills, list):
        return sections
    for section in skills:
        if not isinstance(section, dict):
            continue
        picked: List[str] = []
        for item in section.get("items") or []:
            if not isinstance(item, str):
                continue
            canonical = allowed.get(normalize(item))
            if canonical and canonical not in picked:
                picked.append(canonical)
        if picked:
            sections.append(
                {
                    "title": _clip(section.get("title"), 60, "Compétences"),
                    "items": picked,
                }
            )
    return sections


def _validate_announcement(raw: Any) -> Dict[str, str]:
    """Ce que l'agent a lu dans l'annonce : des champs courts, une famille connue."""
    raw = raw if isinstance(raw, dict) else {}
    return {
        "intitule": _clip(raw.get("intitule"), 140),
        "entreprise": _clip(raw.get("entreprise"), 90),
        "lieu": _clip(raw.get("lieu"), 90),
        "contrat": _clip(raw.get("contrat"), 40),
        "famille": candidate_rules.normalize_family(raw.get("famille")),
    }


def _validate_plan(
    proposed: Dict[str, Any],
    rule_plan: Dict[str, Any],
    master: Dict[str, Any],
    run: AgentResult,
) -> Dict[str, Any]:
    """Conserve le plan de l'agent analyste, en ne vérifiant que sa véracité.

    Python contrôle que chaque identifiant existe dans le profil maître et que
    chaque indice de preuve est atteignable. Il ne réintroduit aucune
    expérience écartée, n'impose aucun minimum et ne réordonne rien : une
    sélection courte est une décision éditoriale, pas un défaut à réparer.
    """
    variants = {item.get("id"): item for item in master.get("cv_variants", []) if item.get("id")}
    variant_id = str(proposed.get("selected_base_variant") or "")
    # Une famille de poste peut porter sa variante (règle du candidat,
    # adaptation_rules.variant_by_job_family) : toute médiation part sur la même base.
    family = candidate_rules.normalize_family((proposed.get("annonce") or {}).get("famille"))
    imposed = candidate_rules.variant_for_family(master, family)
    if imposed in variants:
        variant_id = imposed
    if variant_id not in variants:
        variant_id = str(rule_plan.get("selected_base_variant") or next(iter(variants), "webmaster"))
    # Expériences déclarées dans les consignes : citables dans ce plan comme
    # celles du profil, une fois réduites à ce que le texte du candidat dit.
    declared, declared_warnings = validate_declared(proposed.get("experiences_declarees"), master)
    master = with_declared_experiences(master, declared)
    catalog = master.get("experience_catalog", {})
    renamed = declared_id_map(declared)

    raw_experiences = proposed.get("experience_plan")
    if not isinstance(raw_experiences, list) or not raw_experiences:
        raise CVAgentError(
            "L'agent analyste n'a proposé aucune expérience. Le plan est un choix "
            "éditorial : Python ne le fabrique pas à sa place."
        )

    experience_plan: List[Dict[str, Any]] = []
    seen: set[str] = set()
    unknown: List[str] = []
    for item in raw_experiences:
        if not isinstance(item, dict):
            continue
        exp_id = str(item.get("experience_id") or "")
        exp_id = renamed.get(exp_id, exp_id)
        if exp_id in seen:
            continue
        if exp_id not in catalog or catalog[exp_id].get("retired"):
            unknown.append(exp_id)
            continue
        highlights = catalog[exp_id].get("highlights", [])
        indexes: List[int] = []
        for index in item.get("highlight_indexes", []) or []:
            if isinstance(index, int) and 0 <= index < len(highlights) and index not in indexes:
                indexes.append(index)
        experience_plan.append(
            {
                "experience_id": exp_id,
                "priority": int(item.get("priority") or 0),
                "selection_role": catalog[exp_id].get("cv_role", "core"),
                "reason": _clip(item.get("reason"), 260, "Expérience retenue par l'agent analyste."),
                "highlight_indexes": indexes,
                "highlights": [highlights[index] for index in indexes],
            }
        )
        seen.add(exp_id)
    # Une expérience déclarée dans les consignes est une demande du candidat :
    # elle figure sur le CV même si l'agent l'a omise.
    for entry in declared:
        exp_id = entry["id"]
        if exp_id in seen:
            continue
        indexes = list(range(len(entry["highlights"])))[:3]
        experience_plan.append(
            {
                "experience_id": exp_id,
                "priority": 0,
                "selection_role": "core",
                "reason": "Expérience déclarée dans les consignes du candidat.",
                "highlight_indexes": indexes,
                "highlights": [entry["highlights"][index] for index in indexes],
                "declared": True,
            }
        )
        seen.add(exp_id)
    if not experience_plan:
        raise CVAgentError(
            "Aucune expérience proposée par l'agent analyste n'existe dans le profil "
            f"maître (reçu : {', '.join(unknown) or 'rien'})."
        )

    # Règle candidat (21/10/2026) : certaines expériences forment la colonne
    # vertébrale du parcours et figurent sur tous les CV de la variante, pour
    # que la chronologie 2023 → aujourd'hui reste continue. Chaque entrée est
    # un identifiant, ou une liste d'alternatives dont une seule suffit.
    for required in _required_experiences(master, variant_id):
        options = [required] if isinstance(required, str) else [str(x) for x in required]
        options = [x for x in options if x in catalog and not catalog[x].get("retired")]
        if not options or any(x in seen for x in options):
            continue
        if any(candidate_excludes(master, x) for x in options):
            continue  # le candidat a demandé de la retirer : sa consigne l'emporte
        exp_id = options[0]
        highlights = catalog[exp_id].get("highlights", [])
        indexes = list(range(min(len(highlights), 3)))
        experience_plan.append(
            {
                "experience_id": exp_id,
                "priority": 0,
                "selection_role": catalog[exp_id].get("cv_role", "core"),
                "reason": "Expérience obligatoire pour cette variante (règle du profil maître).",
                "highlight_indexes": indexes,
                "highlights": [highlights[index] for index in indexes],
                "required": True,
            }
        )
        seen.add(exp_id)

    presentation_strategy = _validate_presentation_strategy(
        proposed.get("presentation_strategy"), variant_id, seen, master
    )

    raw_skills = proposed.get("skills_to_emphasize")
    skills = _sanitize_skill_mapping(raw_skills, master, variant_id) if isinstance(raw_skills, dict) else {}

    section_order = [
        str(section)
        for section in (proposed.get("section_order") or [])
        if str(section) in ALLOWED_SECTIONS
    ]
    if not section_order:
        section_order = rule_plan.get(
            "suggested_section_order", ["profile", "skills", "experiences", "projects", "education"]
        )

    project_catalog = master.get("project_catalog", {})
    selected_projects = [
        project_id
        for project_id in _as_string_list(proposed.get("selected_projects"), limit=4)
        if project_id in project_catalog
    ]

    critical_requirements = [
        {
            "requirement": _clip(item.get("requirement"), 120),
            "importance": str(item.get("importance") or "high"),
        }
        for item in (proposed.get("critical_requirements") or [])
        if isinstance(item, dict) and _clip(item.get("requirement"), 120)
    ] or rule_plan.get("critical_requirements", [])

    return {
        "agent": "cv_job_analyzer_ai",
        "agent_run": _agent_run(run),
        "annonce": _validate_announcement(proposed.get("annonce")),
        "selected_base_variant": variant_id,
        "target_title": _clip(proposed.get("target_title"), 90),
        "positioning": _clip(
            proposed.get("positioning"),
            int(master.get("layout_constraints", {}).get("max_profile_chars", 240)),
        ),
        "priority_keywords": _as_string_list(
            proposed.get("priority_keywords") or rule_plan.get("priority_keywords"),
            limit=14,
        ),
        "experience_plan": experience_plan,
        "critical_requirements": critical_requirements,
        # Index déterministe du catalogue de preuves : une entrée de contrôle
        # pour le juge, jamais une sélection éditoriale imposée au rédacteur.
        "evidence_matches": rule_plan.get("evidence_matches", []),
        "presentation_strategy": presentation_strategy,
        "section_order": section_order,
        "selected_projects": selected_projects,
        "skills_to_emphasize": skills,
        "skills_to_reduce": _as_string_list(proposed.get("skills_to_reduce"), limit=8),
        "warnings": _as_string_list(proposed.get("warnings"), limit=8),
        "unknown_experience_ids": unknown,
        "declared_experiences": declared,
        "declared_experience_warnings": declared_warnings,
    }


def _candidate_title(item: Dict[str, Any], master: Dict[str, Any]) -> str:
    """Intitulé d'expérience demandé par le candidat dans ses consignes.

    Les intitulés viennent du profil maître, sauf quand l'agent en propose un
    qui figure mot pour mot dans les consignes du candidat (règle Cundo
    21/10/2026 : la consigne est la source de vérité supérieure).
    """
    title = re.sub(r"\s+", " ", str(item.get("title") or "")).strip()
    text = str(master.get("candidate_instructions_text") or "")
    if title and text and title.lower() in text.lower():
        return title
    return ""


def _required_experiences(master: Dict[str, Any], variant_id: str) -> List[Any]:
    """Expériences obligatoires de la variante (``"*"`` = valeur par défaut)."""
    return candidate_rules.required_experiences(master, variant_id)


def _validate_presentation_strategy(
    proposed: Any,
    variant_id: str,
    planned_ids: Iterable[str],
    master: Dict[str, Any],
) -> Dict[str, Any]:
    """Accepte le regroupement demandé par l'agent s'il est déclaré et cohérent.

    Python ne décide plus de grouper : il refuse un groupe impossible et laisse
    l'agent seul juge de l'opportunité de le faire — sauf pour un groupe marqué
    ``always_group`` dans le profil maître (règle candidat du 21/10/2026) : dès
    que l'agent retient assez de ses missions, elles sont regroupées, quelle que
    soit la variante.
    """
    planned = set(planned_ids)
    for forced_id, forced in (master.get("experience_groups", {}) or {}).items():
        if not isinstance(forced, dict) or not forced.get("always_group"):
            continue
        members = [mid for mid in forced.get("member_ids", []) if mid in planned]
        if len(members) >= int(forced.get("min_selected_members", 2)):
            return {
                "experience_display_mode": forced.get("display_mode", "grouped_missions"),
                "experience_group_id": forced_id,
                "member_ids": members,
            }
    if not isinstance(proposed, dict):
        return {"experience_display_mode": "individual"}
    if str(proposed.get("experience_display_mode") or "individual") != "grouped_missions":
        return {"experience_display_mode": "individual"}
    group_id = str(proposed.get("experience_group_id") or "")
    group = master.get("experience_groups", {}).get(group_id)
    if not isinstance(group, dict) or variant_id not in group.get("allowed_variants", []):
        return {"experience_display_mode": "individual"}
    declared = set(group.get("member_ids", []))
    requested = [
        str(item)
        for item in (proposed.get("member_ids") or [])
        if str(item) in declared and str(item) in set(planned_ids)
    ]
    if len(requested) < int(group.get("min_selected_members", 2)):
        return {"experience_display_mode": "individual"}
    return {
        "experience_display_mode": group.get("display_mode", "grouped_missions"),
        "experience_group_id": group_id,
        "member_ids": requested,
    }


def _cited_text(reference: str, master: Dict[str, Any]) -> str:
    """Le texte d'une preuve citée (« exp_id:index », « consignes_candidat:N », projet)."""
    ref = str(reference or "").strip()
    if ":" in ref:
        owner, _, index = ref.rpartition(":")
        if index.isdigit():
            position = int(index)
            if owner == "consignes_candidat":
                statements = master.get("candidate_statements", []) or []
                return str(statements[position]) if position < len(statements) else ""
            highlights = (master.get("experience_catalog", {}).get(owner) or {}).get("highlights", []) or []
            return str(highlights[position]) if position < len(highlights) else ""
    project = master.get("project_catalog", {}).get(ref) or {}
    return str(project.get("description") or "")


def with_cited_evidence(cv: Dict[str, Any], master: Dict[str, Any]) -> Dict[str, Any]:
    """Le CV à vérifier, chaque puce collée à ses preuves et à leur texte.

    Le vérificateur recevait les puces et ``bullet_sources`` en deux listes à
    recoller par position, et se trompait : cas réel (D2P, 22/10/2026), une
    puce citant ``qualiscope_backend:0`` et ``:5`` refusée parce que « :0 n'est
    pas référencé ». Python fait l'association et joint le texte cité : la
    vérification ne porte plus que sur l'écart de sens.
    """
    view = dict(cv)
    experiences = []
    for exp in cv.get("experiences", []) or []:
        if not isinstance(exp, dict):
            experiences.append(exp)
            continue
        sources = exp.get("bullet_sources") or []
        bullets = []
        for index, bullet in enumerate(exp.get("bullets", []) or []):
            refs = sources[index] if index < len(sources) and isinstance(sources[index], list) else []
            bullets.append({
                "text": bullet,
                "preuves_citees": [{"ref": ref, "texte": _cited_text(ref, master)} for ref in refs],
            })
        entry = {key: value for key, value in exp.items() if key != "bullet_sources"}
        entry["bullets"] = bullets
        experiences.append(entry)
    view["experiences"] = experiences
    return view


def without_contact(value: Dict[str, Any]) -> Dict[str, Any]:
    """Copie sans bloc ``contact`` d'un CV, d'un contenu ``{"cv": ...}`` ou d'un squelette.

    Les coordonnées appartiennent à Python (voir ``_PYTHON_OWNED_PATHS``) : un
    agent n'a rien à en dire, il n'a donc pas à les recevoir.
    """
    if not isinstance(value, dict):
        return value
    copy = {key: item for key, item in value.items() if key != "contact"}
    if isinstance(copy.get("cv"), dict):
        copy["cv"] = {key: item for key, item in copy["cv"].items() if key != "contact"}
    return copy
