"""Contrôles Python purs sur un CV rédigé par les agents IA.

Ce module ne réécrit jamais le contenu éditorial. Il lit une proposition
d'agent (ou un CV déjà assemblé), la compare au profil maître, et renvoie le
contenu d'origine accompagné d'une liste d'erreurs localisées. Aucun fallback,
aucune réinsertion, aucun tri : quand une affirmation n'est pas sourcée, c'est
une erreur rendue au réviseur, pas une donnée que Python fabrique à sa place.

Deux familles d'erreurs cohabitent :

``truth``
    Une affirmation qui ne peut pas être reliée au profil maître. Bloquant.
``format``
    Une contrainte de gabarit (longueur, nombre d'éléments, ordre). Corrigeable
    par une révision, mais interdit l'export final tant qu'elle subsiste.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .job_analyzer import _period_sort_key
from .utils import flatten_skills, normalize

TRUTH = "truth"
FORMAT = "format"

#: Sections acceptées dans ``section_order``.
ALLOWED_SECTIONS = ("profile", "skills", "experiences", "projects", "education")


@dataclass(frozen=True)
class TruthIssue:
    """Une erreur localisée, lisible par un agent réviseur."""

    code: str
    kind: str
    path: str
    detail: str
    reference: str | None = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "kind": self.kind,
            "path": self.path,
            "detail": self.detail,
            "reference": self.reference,
        }


@dataclass
class BulletView:
    text: str
    sources: List[str]
    path: str


@dataclass
class ExperienceView:
    id: str
    path: str
    is_group: bool = False
    member_ids: List[str] = field(default_factory=list)
    bullets: List[BulletView] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Lecture du profil maître
# --------------------------------------------------------------------------- #


def allowed_skill_labels(master: Dict[str, Any]) -> Dict[str, str]:
    """Libellés de compétence autorisés, indexés par forme normalisée."""
    labels: List[str] = list(master.get("skills_confidence", {}).keys())
    for variant in master.get("cv_variants", []):
        labels.extend(flatten_skills(variant.get("skills", {})))
    return {normalize(label): str(label) for label in labels if normalize(label)}


def allowed_education_titles(master: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    catalog: Dict[str, Dict[str, Any]] = {}
    for item in master.get("person", {}).get("education", []):
        if isinstance(item, dict) and normalize(item.get("title")):
            catalog[normalize(item.get("title"))] = item
    return catalog


def _highlights(master: Dict[str, Any], experience_id: str) -> List[str]:
    entry = master.get("experience_catalog", {}).get(experience_id) or {}
    highlights = entry.get("highlights", [])
    return [str(item) for item in highlights] if isinstance(highlights, list) else []


def experience_period(master: Dict[str, Any], experience_id: str) -> Dict[str, Any] | None:
    """Période de référence d'une expérience unitaire ou d'un groupe déclaré."""
    catalog = master.get("experience_catalog", {})
    if experience_id in catalog:
        return catalog[experience_id].get("period")
    group = master.get("experience_groups", {}).get(experience_id)
    return group.get("period") if isinstance(group, dict) else None


# --------------------------------------------------------------------------- #
# Références de provenance
# --------------------------------------------------------------------------- #


def parse_source_reference(raw: Any) -> Tuple[str, str, int | None] | None:
    """Décompose ``experience_id:index`` ou ``project_id``.

    Renvoie ``(kind, identifier, index)`` avec ``kind`` valant ``"experience"``
    ou ``"project"``, ou ``None`` quand la référence est illisible.
    """
    text = str(raw or "").strip()
    if not text:
        return None
    if ":" not in text:
        return ("project", text, None)
    identifier, _, index_text = text.rpartition(":")
    identifier = identifier.strip()
    index_text = index_text.strip()
    if not identifier or not index_text.isdigit():
        return None
    return ("experience", identifier, int(index_text))


def _bullet_sources(raw_bullet: Any, experience_id: str) -> Tuple[str, List[str]]:
    """Lit un bullet au format agent ou au format assemblé.

    Le champ historique ``source_highlight_indexes`` reste lisible pendant la
    migration : il désigne implicitement les highlights de l'expérience qui
    porte le bullet. Cette lecture ne modifie rien, elle traduit.
    """
    if not isinstance(raw_bullet, dict):
        return (str(raw_bullet or ""), [])
    text = str(raw_bullet.get("text") or "")
    raw_sources = raw_bullet.get("sources")
    if isinstance(raw_sources, str):
        raw_sources = [raw_sources]
    if isinstance(raw_sources, list):
        return (text, [str(item).strip() for item in raw_sources if str(item).strip()])
    legacy = raw_bullet.get("source_highlight_indexes", raw_bullet.get("source_highlight_index"))
    if isinstance(legacy, int):
        legacy = [legacy]
    if isinstance(legacy, list):
        return (
            text,
            [f"{experience_id}:{index}" for index in legacy if isinstance(index, int)],
        )
    return (text, [])


def normalize_experiences(cv: Dict[str, Any]) -> List[ExperienceView]:
    """Vue canonique des expériences, quelle que soit la forme d'entrée.

    Accepte la proposition brute d'un agent (``bullets`` = objets sourcés) et
    le CV assemblé (``bullets`` = textes, provenance dans ``bullet_sources``).
    """
    views: List[ExperienceView] = []
    raw_experiences = cv.get("experiences")
    if not isinstance(raw_experiences, list):
        return views
    for position, raw in enumerate(raw_experiences):
        path = f"experiences[{position}]"
        if not isinstance(raw, dict):
            views.append(ExperienceView(id="", path=path))
            continue
        experience_id = str(raw.get("id") or "")
        member_ids = raw.get("source_experience_ids")
        member_ids = [str(item) for item in member_ids] if isinstance(member_ids, list) else []
        view = ExperienceView(
            id=experience_id,
            path=path,
            is_group=bool(member_ids) or bool(raw.get("kind") == "grouped"),
            member_ids=member_ids,
        )
        raw_bullets = raw.get("bullets")
        raw_bullets = raw_bullets if isinstance(raw_bullets, list) else []
        parallel = raw.get("bullet_sources")
        parallel = parallel if isinstance(parallel, list) else []
        for index, raw_bullet in enumerate(raw_bullets):
            text, sources = _bullet_sources(raw_bullet, experience_id)
            if not sources and index < len(parallel):
                candidate = parallel[index]
                if isinstance(candidate, str):
                    candidate = [candidate]
                if isinstance(candidate, list):
                    sources = [str(item).strip() for item in candidate if str(item).strip()]
            view.bullets.append(
                BulletView(text=text, sources=sources, path=f"{path}.bullets[{index}]")
            )
        views.append(view)
    return views


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


def _cv_payload(content: Dict[str, Any]) -> Dict[str, Any]:
    payload = content.get("cv")
    return payload if isinstance(payload, dict) else content


def _cv_text(cv: Dict[str, Any], experiences: Sequence[ExperienceView]) -> str:
    parts: List[str] = [str(cv.get("title") or ""), str(cv.get("profile") or "")]
    for section in cv.get("skills", []) if isinstance(cv.get("skills"), list) else []:
        if isinstance(section, dict):
            parts.append(str(section.get("title") or ""))
            parts.extend(str(item) for item in section.get("items", []))
    for experience in experiences:
        parts.extend(bullet.text for bullet in experience.bullets)
    for project in cv.get("projects", []) if isinstance(cv.get("projects"), list) else []:
        if isinstance(project, dict):
            parts.append(str(project.get("description") or ""))
    return normalize(" ".join(parts))


def _validate_group(
    view: ExperienceView,
    master: Dict[str, Any],
) -> Tuple[List[TruthIssue], List[str]]:
    """Contrôle un bloc groupé et renvoie les membres effectivement autorisés."""
    issues: List[TruthIssue] = []
    group = master.get("experience_groups", {}).get(view.id)
    if not isinstance(group, dict):
        return (
            [
                TruthIssue(
                    "UNKNOWN_EXPERIENCE",
                    TRUTH,
                    view.path,
                    f"« {view.id} » n'est ni une expérience du catalogue ni un groupe déclaré.",
                    view.id,
                )
            ],
            [],
        )
    catalog = master.get("experience_catalog", {})
    declared = [str(item) for item in group.get("member_ids", [])]
    for member in declared:
        if member not in catalog:
            issues.append(
                TruthIssue(
                    "GROUP_MEMBER_NOT_IN_CATALOG",
                    TRUTH,
                    view.path,
                    f"Le groupe « {view.id} » déclare « {member} », absent du catalogue d'expériences.",
                    member,
                )
            )
    used = view.member_ids or declared
    unexpected = [member for member in used if member not in declared]
    for member in unexpected:
        issues.append(
            TruthIssue(
                "UNDECLARED_GROUP_MEMBER",
                TRUTH,
                view.path,
                f"« {member} » n'est pas un membre déclaré du groupe « {view.id} ».",
                member,
            )
        )
    minimum = int(group.get("min_selected_members", 2))
    if len(used) < minimum:
        issues.append(
            TruthIssue(
                "GROUP_TOO_FEW_MEMBERS",
                TRUTH,
                view.path,
                f"Le groupe « {view.id} » exige au moins {minimum} missions, {len(used)} fournie(s).",
                view.id,
            )
        )
    for alternatives in group.get("mutually_exclusive_sets", []):
        present = [member for member in used if member in alternatives]
        if len(present) > 1:
            issues.append(
                TruthIssue(
                    "GROUP_MUTUALLY_EXCLUSIVE",
                    TRUTH,
                    view.path,
                    "Missions mutuellement exclusives affichées ensemble : " + ", ".join(present),
                    view.id,
                )
            )
    return issues, [member for member in used if member in declared and member in catalog]


def _validate_bullets(
    view: ExperienceView,
    allowed_experience_ids: Iterable[str],
    master: Dict[str, Any],
    constraints: Dict[str, Any],
) -> List[TruthIssue]:
    issues: List[TruthIssue] = []
    allowed = set(allowed_experience_ids)
    projects = master.get("project_catalog", {})
    max_chars = int(constraints.get("max_bullet_chars", 145))
    for bullet in view.bullets:
        if not bullet.text.strip():
            issues.append(
                TruthIssue("EMPTY_BULLET", FORMAT, bullet.path, "Puce vide.", view.id)
            )
            continue
        if len(bullet.text) > max_chars:
            issues.append(
                TruthIssue(
                    "BULLET_TOO_LONG",
                    FORMAT,
                    bullet.path,
                    f"Puce de {len(bullet.text)} caractères, limite {max_chars}.",
                    view.id,
                )
            )
        if not bullet.sources:
            issues.append(
                TruthIssue(
                    "BULLET_WITHOUT_SOURCE",
                    TRUTH,
                    bullet.path,
                    "Cette puce ne cite aucune preuve du profil maître.",
                    view.id,
                )
            )
            continue
        for raw in bullet.sources:
            parsed = parse_source_reference(raw)
            if parsed is None:
                issues.append(
                    TruthIssue(
                        "UNKNOWN_SOURCE_REFERENCE",
                        TRUTH,
                        bullet.path,
                        f"Référence illisible « {raw} » : attendu « experience_id:index » ou « project_id ».",
                        raw,
                    )
                )
                continue
            kind, identifier, index = parsed
            if kind == "project":
                if identifier not in projects:
                    issues.append(
                        TruthIssue(
                            "UNKNOWN_SOURCE_REFERENCE",
                            TRUTH,
                            bullet.path,
                            f"Le projet « {identifier} » n'existe pas dans le catalogue.",
                            raw,
                        )
                    )
                continue
            if identifier not in allowed:
                issues.append(
                    TruthIssue(
                        "SOURCE_OUTSIDE_EXPERIENCE",
                        TRUTH,
                        bullet.path,
                        f"« {identifier} » n'est pas une source autorisée pour ce bloc.",
                        raw,
                    )
                )
                continue
            highlights = _highlights(master, identifier)
            if index is None or index >= len(highlights):
                issues.append(
                    TruthIssue(
                        "SOURCE_OUT_OF_RANGE",
                        TRUTH,
                        bullet.path,
                        f"« {identifier} » ne possède pas de preuve n°{index} "
                        f"({len(highlights)} disponible(s)).",
                        raw,
                    )
                )
    return issues


def _validate_skills(
    cv: Dict[str, Any],
    master: Dict[str, Any],
    variant_id: str,
    constraints: Dict[str, Any],
) -> List[TruthIssue]:
    issues: List[TruthIssue] = []
    sections = cv.get("skills")
    if not isinstance(sections, list):
        return issues
    allowed = allowed_skill_labels(master)
    excluded = {
        normalize(skill)
        for skill in master.get("adaptation_rules", {})
        .get("excluded_skills_by_variant", {})
        .get(variant_id, [])
    }
    max_sections = int(constraints.get("max_skill_sections", 4))
    max_items = int(constraints.get("max_skill_items_total", 10))
    if len(sections) > max_sections:
        issues.append(
            TruthIssue(
                "TOO_MANY_SKILL_SECTIONS",
                FORMAT,
                "skills",
                f"{len(sections)} blocs de compétences, limite {max_sections}.",
            )
        )
    total = 0
    for position, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        for item_index, item in enumerate(section.get("items", []) or []):
            total += 1
            path = f"skills[{position}].items[{item_index}]"
            key = normalize(item)
            if key not in allowed:
                issues.append(
                    TruthIssue(
                        "UNKNOWN_SKILL",
                        TRUTH,
                        path,
                        f"« {item} » ne correspond à aucun libellé autorisé du profil maître.",
                        str(item),
                    )
                )
            elif key in excluded:
                issues.append(
                    TruthIssue(
                        "EXCLUDED_SKILL",
                        TRUTH,
                        path,
                        f"« {item} » est exclue pour la variante {variant_id}.",
                        str(item),
                    )
                )
    if total > max_items:
        issues.append(
            TruthIssue(
                "TOO_MANY_SKILLS",
                FORMAT,
                "skills",
                f"{total} compétences affichées, limite {max_items}.",
            )
        )
    return issues


def _validate_projects(
    cv: Dict[str, Any],
    master: Dict[str, Any],
    constraints: Dict[str, Any],
) -> List[TruthIssue]:
    issues: List[TruthIssue] = []
    projects = cv.get("projects")
    if not isinstance(projects, list):
        return issues
    catalog = master.get("project_catalog", {})
    max_projects = int(constraints.get("max_projects", 1))
    if len(projects) > max_projects:
        issues.append(
            TruthIssue(
                "TOO_MANY_PROJECTS",
                FORMAT,
                "projects",
                f"{len(projects)} projets affichés, limite {max_projects}.",
            )
        )
    for position, project in enumerate(projects):
        path = f"projects[{position}]"
        if not isinstance(project, dict):
            continue
        project_id = str(project.get("id") or "")
        source = catalog.get(project_id)
        if source is None:
            issues.append(
                TruthIssue(
                    "UNKNOWN_PROJECT",
                    TRUTH,
                    path,
                    f"« {project_id} » n'existe pas dans le catalogue de projets.",
                    project_id,
                )
            )
            continue
        allowed = {normalize(item) for item in source.get("technologies", [])}
        for item in project.get("technologies", []) or []:
            if normalize(item) not in allowed:
                issues.append(
                    TruthIssue(
                        "UNKNOWN_PROJECT_TECHNOLOGY",
                        TRUTH,
                        path,
                        f"« {item} » n'est pas une technologie déclarée du projet « {project_id} ».",
                        str(item),
                    )
                )
    return issues


def _rendering_matches_catalog(rendered: str, catalog: Dict[str, Dict[str, Any]]) -> bool:
    """Un rendu composé est couvert par un titre du catalogue.

    Le créateur rend les formations sous forme composée — « 2026 — Titre
    Professionnel Concepteur Développeur d'Applications (niveau 6, VAE en
    cours) » — tandis que `person.education` porte des champs séparés. Le
    rendu peut ajouter de l'habillage (année, niveau, statut, école) ; il ne
    peut pas remplacer le titre par un autre. La vérification est donc : le
    titre maître figure-t-il dans le rendu, avec des délimiteurs de mots ?
    Le jugement sémique (niveau ou statut contradictoire) reste au checker IA.
    """
    if not rendered:
        return False
    for master_title in catalog:
        if not master_title:
            continue
        pattern = r"(?:^|[^\w])" + re.escape(master_title) + r"(?:[^\w]|$)"
        if re.search(pattern, rendered):
            return True
    return False


def _validate_education(
    cv: Dict[str, Any],
    master: Dict[str, Any],
    constraints: Dict[str, Any],
) -> List[TruthIssue]:
    issues: List[TruthIssue] = []
    education = cv.get("education")
    if not isinstance(education, list):
        return issues
    catalog = allowed_education_titles(master)
    max_items = int(constraints.get("max_education_items", 4))
    if len(education) > max_items:
        issues.append(
            TruthIssue(
                "TOO_MANY_EDUCATION_ITEMS",
                FORMAT,
                "education",
                f"{len(education)} formations affichées, limite {max_items}.",
            )
        )
    for position, item in enumerate(education):
        title = item.get("title") if isinstance(item, dict) else item
        rendered = normalize(title)
        if rendered not in catalog and not _rendering_matches_catalog(rendered, catalog):
            issues.append(
                TruthIssue(
                    "UNKNOWN_EDUCATION",
                    TRUTH,
                    f"education[{position}]",
                    f"« {title} » ne figure pas dans person.education.",
                    str(title),
                )
            )
    return issues


def _validate_order(
    views: Sequence[ExperienceView],
    master: Dict[str, Any],
) -> List[TruthIssue]:
    """Signale un ordre non antéchronologique sans jamais le corriger."""
    keys = [_period_sort_key(experience_period(master, view.id)) for view in views]
    for position in range(1, len(keys)):
        if keys[position - 1] < keys[position]:
            return [
                TruthIssue(
                    "EXPERIENCE_ORDER_NOT_ANTICHRONOLOGICAL",
                    FORMAT,
                    f"experiences[{position}]",
                    f"« {views[position].id} » est plus récente que « {views[position - 1].id} » "
                    "mais apparaît après : l'ordre attendu est antéchronologique.",
                    views[position].id,
                )
            ]
    return []


def validate_cv_content(
    content: Dict[str, Any],
    master: Dict[str, Any],
    plan: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Valide un CV sans le modifier.

    Renvoie le contenu reçu tel quel, plus la liste des erreurs. Une erreur de
    vérité interdit la publication ; une erreur de format est corrigeable par
    une révision mais interdit l'export final tant qu'elle subsiste.
    """
    cv = _cv_payload(content)
    constraints = master.get("layout_constraints", {})
    variant_id = str((plan or {}).get("selected_base_variant") or content.get("base_variant") or "")
    catalog = master.get("experience_catalog", {})
    issues: List[TruthIssue] = []

    views = normalize_experiences(cv)
    if not views:
        issues.append(
            TruthIssue(
                "EMPTY_CV",
                TRUTH,
                "experiences",
                "Le CV ne présente aucune expérience : l'agent doit en sélectionner au moins une.",
            )
        )

    max_experiences = int(constraints.get("max_experiences", 4))
    by_variant = constraints.get("max_experiences_by_variant", {})
    max_experiences = int(by_variant.get(variant_id, max_experiences))
    if len(views) > max_experiences:
        issues.append(
            TruthIssue(
                "TOO_MANY_EXPERIENCES",
                FORMAT,
                "experiences",
                f"{len(views)} blocs d'expérience, limite {max_experiences} pour la variante {variant_id or 'par défaut'}.",
            )
        )

    max_bullets = int(constraints.get("max_bullets_per_experience", 3))
    seen: set[str] = set()
    for view in views:
        if not view.id:
            issues.append(
                TruthIssue(
                    "UNKNOWN_EXPERIENCE", TRUTH, view.path, "Bloc d'expérience sans identifiant."
                )
            )
            continue
        if view.id in seen:
            issues.append(
                TruthIssue(
                    "DUPLICATE_EXPERIENCE",
                    TRUTH,
                    view.path,
                    f"« {view.id} » apparaît plusieurs fois.",
                    view.id,
                )
            )
            continue
        seen.add(view.id)

        if view.id in catalog and not view.is_group:
            allowed_sources = [view.id]
        elif view.id in catalog and view.is_group:
            issues.append(
                TruthIssue(
                    "UNKNOWN_EXPERIENCE",
                    TRUTH,
                    view.path,
                    f"« {view.id} » est une expérience unitaire, elle ne peut pas porter "
                    "source_experience_ids.",
                    view.id,
                )
            )
            allowed_sources = [view.id]
        else:
            group_issues, allowed_sources = _validate_group(view, master)
            issues.extend(group_issues)

        if not view.bullets:
            issues.append(
                TruthIssue(
                    "EMPTY_EXPERIENCE",
                    FORMAT,
                    view.path,
                    f"« {view.id} » est affichée sans aucune puce.",
                    view.id,
                )
            )
        elif len(view.bullets) > max_bullets:
            issues.append(
                TruthIssue(
                    "TOO_MANY_BULLETS",
                    FORMAT,
                    view.path,
                    f"{len(view.bullets)} puces pour « {view.id} », limite {max_bullets}.",
                    view.id,
                )
            )
        issues.extend(_validate_bullets(view, allowed_sources, master, constraints))

    issues.extend(_validate_order(views, master))
    issues.extend(_validate_skills(cv, master, variant_id, constraints))
    issues.extend(_validate_projects(cv, master, constraints))
    issues.extend(_validate_education(cv, master, constraints))

    profile = str(cv.get("profile") or "")
    max_profile = int(constraints.get("max_profile_chars", 240))
    if len(profile) > max_profile:
        issues.append(
            TruthIssue(
                "PROFILE_TOO_LONG",
                FORMAT,
                "profile",
                f"Accroche de {len(profile)} caractères, limite {max_profile}.",
            )
        )

    text = _cv_text(cv, views)
    for claim in master.get("forbidden_claims", []):
        if normalize(claim) and normalize(claim) in text:
            issues.append(
                TruthIssue(
                    "FORBIDDEN_CLAIM",
                    TRUTH,
                    "cv",
                    f"Affirmation interdite présente dans le CV : « {claim} ».",
                    str(claim),
                )
            )

    section_order = cv.get("section_order")
    if isinstance(section_order, list):
        for section in section_order:
            if str(section) not in ALLOWED_SECTIONS:
                issues.append(
                    TruthIssue(
                        "UNKNOWN_SECTION",
                        FORMAT,
                        "section_order",
                        f"Section inconnue « {section} ».",
                        str(section),
                    )
                )

    payload = [issue.as_dict() for issue in issues]
    truth_issues = [item for item in payload if item["kind"] == TRUTH]
    format_issues = [item for item in payload if item["kind"] == FORMAT]
    return {
        "ok": not payload,
        "truthful": not truth_issues,
        "issues": payload,
        "truth_issues": truth_issues,
        "format_issues": format_issues,
        "content": content,
    }


def sourced_experience_ids(cv: Dict[str, Any]) -> List[str]:
    """Identifiants réellement représentés, un groupe comptant pour ses membres.

    Sert aux mesures de couverture : un bloc groupé de trois missions prouve
    trois missions, pas une seule.
    """
    result: List[str] = []
    for view in normalize_experiences(cv):
        candidates = view.member_ids if view.is_group and view.member_ids else [view.id]
        for candidate in candidates:
            if candidate and candidate not in result:
                result.append(candidate)
    return result
