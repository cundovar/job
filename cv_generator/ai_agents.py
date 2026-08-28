from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Protocol

from openai import OpenAI

from cv_generator.cv_creator import create_cv_draft
from cv_generator.cv_quality_checker import review_cv as review_cv_rules
from cv_generator.job_analyzer import _select_experience_mix, analyze_job_for_cv as analyze_job_rules
from cv_generator.utils import compact_items, flatten_skills, normalize, period_to_text
from utils.ai_role_routing import AIRouteStep, legacy_route, load_role_route
from utils.cli_agent_bridge import CLIAgentBridgeClient


class CVAgentError(RuntimeError):
    """Raised when the AI CV chain cannot return a safe, usable result."""


@dataclass(frozen=True)
class AgentResult:
    data: Dict[str, Any]
    provider: str
    model: str


class AgentClient(Protocol):
    def complete_json(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        payload: Dict[str, Any],
    ) -> AgentResult | Dict[str, Any]: ...


def _parse_json_response(content: str) -> Dict[str, Any]:
    raw = (content or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise CVAgentError("L'agent IA n'a pas renvoyé un objet JSON.")
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise CVAgentError("Le JSON renvoyé par l'agent IA est invalide.") from exc
    if not isinstance(parsed, dict):
        raise CVAgentError("L'agent IA doit renvoyer un objet JSON.")
    return parsed


class CVLLMClient:
    """Execute the provider/model fallback route configured for each AI role."""

    def __init__(self, bridge_client: CLIAgentBridgeClient | None = None) -> None:
        timeout = float(os.getenv("CV_AI_TIMEOUT_SECONDS", os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "60")))
        self._cli_bridge = bridge_client or CLIAgentBridgeClient()
        provider_override = os.getenv("CV_AI_PROVIDER_ORDER")
        self._provider_order = (
            [item.strip().lower() for item in provider_override.split(",") if item.strip()]
            if provider_override
            else None
        )
        deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        self._deepseek = (
            OpenAI(
                api_key=deepseek_key,
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                timeout=timeout,
            )
            if deepseek_key
            else None
        )
        self._deepseek_model = os.getenv(
            "CV_DEEPSEEK_MODEL",
            os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        )
        self._claude_model = os.getenv("CV_CLAUDE_MODEL", "claude-sonnet-4-6")
        self._temperature = float(os.getenv("CV_AI_TEMPERATURE", "0.2"))
        self._max_tokens = int(os.getenv("CV_AI_MAX_TOKENS", "5000"))
        self._anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    def _call_cli_bridge(
        self,
        agent_name: str,
        system_prompt: str,
        payload: Dict[str, Any],
        preferred_provider: str | None = None,
        preferred_model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> AgentResult:
        result = self._cli_bridge.complete_json(
            agent_name=agent_name,
            system_prompt=system_prompt,
            payload=payload,
            preferred_provider=preferred_provider,
            preferred_model=preferred_model,
            reasoning_effort=reasoning_effort,
        )
        return AgentResult(
            data=result.data,
            provider=result.provider,
            model=result.model,
        )

    def _call_deepseek(
        self,
        system_prompt: str,
        user_message: str,
        model: str | None = None,
    ) -> AgentResult:
        if self._deepseek is None:
            raise CVAgentError("DEEPSEEK_API_KEY absente")
        selected_model = model or self._deepseek_model
        response = self._deepseek.chat.completions.create(
            model=selected_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        content = response.choices[0].message.content or ""
        return AgentResult(_parse_json_response(content), "deepseek", selected_model)

    def _call_claude(
        self,
        system_prompt: str,
        user_message: str,
        model: str | None = None,
    ) -> AgentResult:
        if not self._anthropic_key:
            raise CVAgentError("ANTHROPIC_API_KEY absente")
        try:
            import anthropic
        except ImportError as exc:
            raise CVAgentError("Le paquet anthropic n'est pas installé") from exc
        client = anthropic.Anthropic(api_key=self._anthropic_key)
        selected_model = model or self._claude_model
        response = client.messages.create(
            model=selected_model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        content = "".join(block.text for block in response.content if hasattr(block, "text"))
        return AgentResult(_parse_json_response(content), "anthropic", selected_model)

    def _route_for(self, agent_name: str) -> List[AIRouteStep]:
        if self._provider_order is not None:
            return legacy_route(self._provider_order)
        return load_role_route(agent_name)

    def complete_json(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        payload: Dict[str, Any],
    ) -> AgentResult:
        user_message = (
            f"AGENT: {agent_name}\n"
            "Voici les données JSON autorisées. Réponds uniquement avec l'objet JSON demandé.\n\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )
        errors: List[str] = []
        for step in self._route_for(agent_name):
            provider = step.provider
            try:
                if provider in {"cli", "bridge"}:
                    return self._call_cli_bridge(agent_name, system_prompt, payload)
                if provider == "codex_cli":
                    return self._call_cli_bridge(
                        agent_name,
                        system_prompt,
                        payload,
                        preferred_provider="codex",
                        preferred_model=step.model,
                        reasoning_effort=step.reasoning_effort,
                    )
                if provider == "claude_cli":
                    return self._call_cli_bridge(
                        agent_name,
                        system_prompt,
                        payload,
                        preferred_provider="claude",
                        preferred_model=step.model,
                    )
                if provider == "deepseek":
                    return self._call_deepseek(system_prompt, user_message, step.model)
                if provider in {"claude", "anthropic"}:
                    return self._call_claude(system_prompt, user_message, step.model)
                errors.append(f"{provider}: fournisseur inconnu")
            except Exception as exc:
                errors.append(f"{provider}: {exc}")
        raise CVAgentError("Aucun agent IA disponible. " + " | ".join(errors))


ANALYZER_PROMPT = """
Tu es l'agent d'analyse d'annonce pour un générateur de CV français.
Lis toute l'annonce et la source de vérité du candidat. Produis un plan d'adaptation précis.
Tu peux sélectionner et hiérarchiser, jamais inventer. Les identifiants d'expériences et les
indices de preuves doivent exister dans source_verite. Conserve les vrais intitulés de poste.
Le titre cible et le positionnement peuvent être adaptés, sans augmenter le niveau réel.
N'inclus une expérience que si elle apporte une preuve explicite à un critère de l'annonce.
Il est préférable de retenir moins d'expériences plutôt que de remplir les emplacements avec
des expériences faibles ou hors sujet. Respecte la visibilité conditionnelle de la source.

JSON attendu:
{
  "selected_base_variant": "id existant",
  "target_title": "titre du CV",
  "positioning": "accroche proposée",
  "priority_keywords": ["..."],
  "experience_plan": [
    {"experience_id":"...","priority":10,"reason":"...","highlight_indexes":[0,1]}
  ],
  "skills_to_emphasize": {"nom_section":["compétence exacte de la source"]},
  "skills_to_reduce": ["..."],
  "warnings": ["..."]
}
""".strip()


CREATOR_PROMPT = """
Tu es l'agent rédacteur du CV. Rédige un CV ciblé et crédible en français à partir du plan,
du brouillon structurel et de la source de vérité. Tu peux reformuler une preuve, mais pas
ajouter de mission, résultat, chiffre, outil, niveau, date ou diplôme absent de la source.
Les intitulés d'expériences ne sont jamais réécrits. Chaque puce doit citer les indices des
highlights qui la prouvent. Les compétences doivent reprendre exactement un libellé autorisé.
Respecte strictement les limites Canva fournies.

JSON attendu:
{
  "title":"...",
  "profile":"...",
  "skills":[{"title":"...","items":["libellé exact"]}],
  "experiences":[
    {"id":"...","bullets":[{"text":"...","source_highlight_indexes":[0]}]}
  ],
  "projects":[{"id":"...","description":"reformulation fidèle"}]
}
""".strip()


REVIEWER_PROMPT = """
Tu es l'agent juge du CV. Sois sévère et factuel. Compare l'annonce, le CV, le plan et la
source de vérité. Évalue: adéquation réelle, mots-clés ATS, absence d'invention, respect des
intitulés, crédibilité du niveau, clarté, concision et contraintes Canva. Une compétence de
l'annonce absente du profil est un écart, pas une compétence à ajouter. Signale précisément
chaque problème et propose une correction fondée sur la source. Ne produis aucun score libre:
Python calcule les notes finales depuis les problèmes et preuves structurés.

JSON attendu:
{
  "strengths":["..."],
  "problems":[{"severity":"high|medium|low","section":"...","problem":"...","suggested_fix":"..."}],
  "missing_keywords":["..."],
  "overrepresented_keywords":["..."],
  "forbidden_claims_found":["..."],
  "verdict":"..."
}
""".strip()


REVISER_PROMPT = """
Tu es l'agent réviseur final. Applique les corrections du juge sans inventer et sans modifier
les vrais intitulés d'expérience. Préserve la provenance de chaque puce avec ses indices de
highlights. N'ajoute que des compétences dont le libellé exact existe dans la source.
Respecte les limites Canva. Retourne le même schéma JSON que l'agent rédacteur:
title, profile, skills, experiences avec bullets {text, source_highlight_indexes}, projects.
""".strip()


def _agent_call(
    client: AgentClient,
    agent_name: str,
    system_prompt: str,
    payload: Dict[str, Any],
) -> AgentResult:
    raw = client.complete_json(
        agent_name=agent_name,
        system_prompt=system_prompt,
        payload=payload,
    )
    if isinstance(raw, AgentResult):
        return raw
    if isinstance(raw, dict):
        return AgentResult(raw, "injected", "test-or-custom")
    raise CVAgentError(f"Réponse invalide de l'agent {agent_name}")


def _truth_context(master: Dict[str, Any]) -> Dict[str, Any]:
    person = master.get("person", {})
    return {
        "usage": master.get("usage", {}),
        "agent_contracts": master.get("agent_contracts", {}),
        "person": {
            "display_name": person.get("display_name"),
            "location": person.get("location"),
            "languages": person.get("languages", []),
            "education": person.get("education", []),
            "eligibility": person.get("eligibility", {}),
        },
        "positioning": master.get("positioning", {}),
        "cv_variants": master.get("cv_variants", []),
        "skills_confidence": master.get("skills_confidence", {}),
        "experience_catalog": master.get("experience_catalog", {}),
        "project_catalog": master.get("project_catalog", {}),
        "approved_phrases": master.get("approved_phrases", {}),
        "forbidden_claims": master.get("forbidden_claims", []),
        "layout_constraints": master.get("layout_constraints", {}),
    }


def _agent_run(result: AgentResult) -> Dict[str, str]:
    return {"provider": result.provider, "model": result.model}


def _clip(value: Any, limit: int, fallback: str = "") -> str:
    text = re.sub(r"\s+", " ", str(value or fallback)).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip(" ,;:") + "…"


def _as_string_list(value: Any, limit: int = 20) -> List[str]:
    if not isinstance(value, list):
        return []
    return compact_items((str(item) for item in value), limit=limit)


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


def _sanitize_skill_mapping(value: Any, master: Dict[str, Any]) -> Dict[str, List[str]]:
    if not isinstance(value, dict):
        return {}
    allowed = _allowed_skills(master)
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
            if canonical and canonical not in picked:
                picked.append(canonical)
            if len(picked) >= min(8, max_items - used):
                break
        if picked:
            result[_clip(section, 60, "Compétences")] = picked
            used += len(picked)
    return result


def _period_key(period: Any) -> tuple[str, str]:
    if not isinstance(period, dict):
        return ("0000-00", "0000-00")
    start = str(period.get("start") or "0000-00")
    if start != "0000-00" and "-" not in start:
        start += "-01"
    end = "9999-12" if period.get("end") is None and period.get("start") else str(period.get("end") or "0000-00")
    if end != "0000-00" and "-" not in end:
        end += "-12"
    return end, start


def _sanitize_plan(
    proposed: Dict[str, Any],
    rule_plan: Dict[str, Any],
    master: Dict[str, Any],
    run: AgentResult,
) -> Dict[str, Any]:
    variants = {item.get("id"): item for item in master.get("cv_variants", []) if item.get("id")}
    variant_id = str(proposed.get("selected_base_variant") or "")
    if variant_id not in variants:
        variant_id = str(rule_plan.get("selected_base_variant") or next(iter(variants), "webmaster"))
    selected = variants.get(variant_id, {})
    catalog = master.get("experience_catalog", {})
    rule_by_id = {item.get("experience_id"): item for item in rule_plan.get("experience_plan", [])}
    experience_plan: List[Dict[str, Any]] = []
    seen = set()
    raw_experiences = proposed.get("experience_plan")
    if not isinstance(raw_experiences, list):
        raw_experiences = []
    for item in raw_experiences:
        if not isinstance(item, dict):
            continue
        exp_id = item.get("experience_id")
        if exp_id not in catalog or exp_id in seen:
            continue
        visibility = str(catalog[exp_id].get("visibility") or "default")
        if visibility.startswith("only_") and exp_id not in rule_by_id:
            continue
        highlights = catalog[exp_id].get("highlights", [])
        indexes = []
        for index in item.get("highlight_indexes", []):
            if isinstance(index, int) and 0 <= index < len(highlights) and index not in indexes:
                indexes.append(index)
        if not indexes:
            rule_highlights = rule_by_id.get(exp_id, {}).get("highlights", [])
            indexes = [highlights.index(text) for text in rule_highlights if text in highlights][:3]
        if not indexes:
            indexes = list(range(min(3, len(highlights))))
        experience_plan.append(
            {
                "experience_id": exp_id,
                "priority": int(item.get("priority") or 0),
                "selection_role": rule_by_id.get(exp_id, {}).get("selection_role", "core"),
                "reason": _clip(item.get("reason"), 260, "Expérience pertinente pour l'annonce."),
                "highlight_indexes": indexes[:3],
                "highlights": [highlights[index] for index in indexes[:3]],
            }
        )
        seen.add(exp_id)
    if not experience_plan:
        for item in rule_plan.get("experience_plan", []):
            exp_id = item.get("experience_id")
            if exp_id not in catalog:
                continue
            highlights = catalog[exp_id].get("highlights", [])
            indexes = [highlights.index(text) for text in item.get("highlights", []) if text in highlights][:3]
            experience_plan.append({**item, "highlight_indexes": indexes})
            seen.add(exp_id)
    for rule_item in rule_plan.get("experience_plan", []):
        exp_id = rule_item.get("experience_id")
        if rule_item.get("selection_role") != "complementary" or exp_id in seen or exp_id not in catalog:
            continue
        highlights = catalog[exp_id].get("highlights", [])
        indexes = [highlights.index(text) for text in rule_item.get("highlights", []) if text in highlights][:3]
        experience_plan.append({**rule_item, "highlight_indexes": indexes})
        seen.add(exp_id)
    max_experiences = int(master.get("layout_constraints", {}).get("max_experiences", 4))
    experience_plan = _select_experience_mix(experience_plan, catalog, max_experiences)
    experience_plan.sort(
        key=lambda item: _period_key(catalog.get(item["experience_id"], {}).get("period")),
        reverse=True,
    )
    skills = _sanitize_skill_mapping(proposed.get("skills_to_emphasize"), master)
    if not skills:
        skills = _sanitize_skill_mapping(selected.get("skills", {}), master)
    title_default = (
        master.get("positioning", {}).get("title_variants", {}).get(variant_id)
        or selected.get("title")
        or rule_plan.get("target_title")
        or "Développeur web / Webmaster"
    )
    profile_default = (
        master.get("positioning", {}).get("summary_variants", {}).get(variant_id)
        or selected.get("profile")
        or rule_plan.get("positioning")
        or ""
    )
    return {
        "agent": "cv_job_analyzer_ai",
        "agent_run": _agent_run(run),
        "selected_base_variant": variant_id,
        "target_title": _clip(proposed.get("target_title"), 90, str(title_default)),
        "positioning": _clip(
            proposed.get("positioning"),
            int(master.get("layout_constraints", {}).get("max_profile_chars", 240)),
            str(profile_default),
        ),
        "priority_keywords": _as_string_list(
            proposed.get("priority_keywords") or rule_plan.get("priority_keywords"),
            limit=14,
        ),
        "experience_plan": experience_plan,
        "skills_to_emphasize": skills,
        "skills_to_reduce": _as_string_list(proposed.get("skills_to_reduce"), limit=8),
        "warnings": _as_string_list(proposed.get("warnings"), limit=8),
    }


def _remove_forbidden(text: str, forbidden: Iterable[Any]) -> str:
    result = text
    for claim in forbidden:
        claim_text = str(claim or "").strip()
        if claim_text:
            result = re.sub(re.escape(claim_text), "", result, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", result).strip(" ,;:-")


def _sanitize_skill_sections(value: Any, base_cv: Dict[str, Any], master: Dict[str, Any]) -> List[Dict[str, Any]]:
    mapping: Dict[str, List[str]] = {}
    if isinstance(value, list):
        for section in value:
            if isinstance(section, dict):
                mapping[str(section.get("title") or "Compétences")] = section.get("items", [])
    sanitized = _sanitize_skill_mapping(mapping, master)
    if not sanitized:
        return base_cv.get("skills", [])
    return [{"title": title, "items": items} for title, items in sanitized.items()]


def _source_indexes(value: Any, max_index: int) -> List[int]:
    if isinstance(value, int):
        value = [value]
    if not isinstance(value, list):
        return []
    result = []
    for index in value:
        if isinstance(index, int) and 0 <= index < max_index and index not in result:
            result.append(index)
    return result


def _sanitize_cv_content(
    proposed: Dict[str, Any],
    job: Dict[str, Any],
    master: Dict[str, Any],
    plan: Dict[str, Any],
    base_draft: Dict[str, Any],
    run: AgentResult,
    agent_name: str,
) -> Dict[str, Any]:
    base_cv = base_draft.get("cv", {})
    constraints = master.get("layout_constraints", {})
    forbidden = master.get("forbidden_claims", [])
    catalog = master.get("experience_catalog", {})
    plan_by_id = {item.get("experience_id"): item for item in plan.get("experience_plan", [])}
    proposed_experiences = {
        item.get("id"): item
        for item in proposed.get("experiences", [])
        if isinstance(item, dict) and item.get("id") in plan_by_id
    }
    experiences: List[Dict[str, Any]] = []
    grounding: List[Dict[str, Any]] = []
    max_bullets = int(constraints.get("max_bullets_per_experience", 3))
    max_chars = int(constraints.get("max_bullet_chars", 145))
    for plan_item in plan.get("experience_plan", []):
        exp_id = plan_item.get("experience_id")
        source = catalog.get(exp_id)
        proposed_exp = proposed_experiences.get(exp_id)
        if not source or not proposed_exp:
            continue
        highlights = source.get("highlights", [])
        allowed_indexes = set(plan_item.get("highlight_indexes") or range(len(highlights)))
        bullets: List[str] = []
        for bullet in proposed_exp.get("bullets", []):
            if not isinstance(bullet, dict):
                continue
            indexes = _source_indexes(
                bullet.get("source_highlight_indexes", bullet.get("source_highlight_index")),
                len(highlights),
            )
            indexes = [index for index in indexes if index in allowed_indexes]
            if not indexes:
                continue
            text = _remove_forbidden(_clip(bullet.get("text"), max_chars), forbidden)
            if not text or normalize(text) in {normalize(existing) for existing in bullets}:
                continue
            bullets.append(text)
            grounding.append(
                {
                    "experience_id": exp_id,
                    "bullet": text,
                    "source_highlight_indexes": indexes,
                    "source_highlights": [highlights[index] for index in indexes],
                }
            )
            if len(bullets) >= max_bullets:
                break
        if bullets:
            experiences.append(
                {
                    "id": exp_id,
                    "organization": source.get("organization", ""),
                    "title": source.get("title", ""),
                    "period": period_to_text(source.get("period")),
                    "bullets": bullets,
                    "links": source.get("links", [])[:2],
                }
            )
    if not experiences:
        raise CVAgentError(f"L'agent {agent_name} n'a produit aucune expérience correctement sourcée.")

    base_projects = {item.get("id"): item for item in base_cv.get("projects", [])}
    projects: List[Dict[str, Any]] = []
    for item in proposed.get("projects", []):
        if not isinstance(item, dict):
            continue
        project_id = item.get("id")
        source = master.get("project_catalog", {}).get(project_id)
        if project_id not in base_projects or not source:
            continue
        projects.append(
            {
                "id": project_id,
                "title": source.get("title", ""),
                "year": source.get("year"),
                "description": _remove_forbidden(
                    _clip(item.get("description"), 300, str(source.get("description", ""))),
                    forbidden,
                ),
                "technologies": source.get("technologies", []),
            }
        )
        if len(projects) >= int(constraints.get("max_projects", 1)):
            break

    profile = _remove_forbidden(
        _clip(
            proposed.get("profile"),
            int(constraints.get("max_profile_chars", 240)),
            str(base_cv.get("profile", "")),
        ),
        forbidden,
    )
    cv = {
        "title": _remove_forbidden(
            _clip(proposed.get("title"), 90, str(base_cv.get("title", ""))),
            forbidden,
        ),
        "profile": profile,
        "contact": base_cv.get("contact", {}),
        "location": base_cv.get("location", ""),
        "skills": _sanitize_skill_sections(proposed.get("skills"), base_cv, master),
        "experiences": experiences,
        "projects": projects,
        "education": base_cv.get("education", []),
        "languages": base_cv.get("languages", []),
    }
    return {
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
        "canva_copy_blocks": {
            "title": cv["title"],
            "profile": cv["profile"],
            "skills": cv["skills"],
            "experiences": cv["experiences"],
            "projects": cv["projects"],
        },
    }


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
        problem = _clip(item.get("problem"), 360)
        if not problem:
            continue
        result.append(
            {
                "severity": severity,
                "section": _clip(item.get("section"), 80, "general"),
                "problem": problem,
                "suggested_fix": _clip(item.get("suggested_fix"), 360),
            }
        )
    return result[:20]


def _merge_review(
    proposed: Dict[str, Any],
    deterministic: Dict[str, Any],
    run: AgentResult,
) -> Dict[str, Any]:
    problems = _normalize_problems(proposed.get("problems"))
    known = {(item["section"], item["problem"]) for item in problems}
    for item in _normalize_problems(deterministic.get("problems")):
        key = (item["section"], item["problem"])
        if key not in known:
            problems.append(item)
            known.add(key)
    missing = compact_items(
        [
            *_as_string_list(proposed.get("missing_keywords"), 20),
            *_as_string_list(deterministic.get("missing_keywords"), 20),
        ],
        limit=20,
    )
    forbidden = compact_items(
        [
            *_as_string_list(proposed.get("forbidden_claims_found"), 20),
            *_as_string_list(deterministic.get("forbidden_claims_found"), 20),
        ],
        limit=20,
    )
    quality_score = _int_score(deterministic.get("quality_score"), 0)
    ats_score = _int_score(deterministic.get("ats_score"), 0)
    has_high = any(item.get("severity") == "high" for item in problems)
    if forbidden or has_high or quality_score < 75:
        status = "needs_revision"
    elif problems or quality_score < 90:
        status = "needs_minor_revision"
    else:
        status = "validated"
    return {
        "agent": "cv_quality_checker_ai",
        "agent_run": _agent_run(run),
        "quality_score": quality_score,
        "ats_score": ats_score,
        "status": status,
        "strengths": _as_string_list(proposed.get("strengths"), 10),
        "problems": problems,
        "missing_keywords": missing,
        "overrepresented_keywords": _as_string_list(proposed.get("overrepresented_keywords"), 20),
        "forbidden_claims_found": forbidden,
        "verdict": _clip(
            proposed.get("verdict"),
            500,
            "Validé" if status == "validated" else "Corriger puis relire",
        ),
        "python_guardrail_review": deterministic,
    }


class AICVPipeline:
    def __init__(self, client: AgentClient | None = None) -> None:
        self.client = client or CVLLMClient()

    def analyze(self, job: Dict[str, Any], master: Dict[str, Any]) -> Dict[str, Any]:
        rule_plan = analyze_job_rules(job, master)
        result = _agent_call(
            self.client,
            "cv_job_analyzer",
            ANALYZER_PROMPT,
            {
                "annonce_complete": job,
                "source_verite": _truth_context(master),
                "preanalyse_python": rule_plan,
            },
        )
        return _sanitize_plan(result.data, rule_plan, master, result)

    def create(
        self,
        job: Dict[str, Any],
        master: Dict[str, Any],
        plan: Dict[str, Any],
    ) -> Dict[str, Any]:
        base = create_cv_draft(job, master, plan)
        result = _agent_call(
            self.client,
            "cv_creator",
            CREATOR_PROMPT,
            {
                "annonce_complete": job,
                "source_verite": _truth_context(master),
                "plan_adaptation": plan,
                "brouillon_structurel_python": base,
            },
        )
        return _sanitize_cv_content(
            result.data,
            job,
            master,
            plan,
            base,
            result,
            "cv_creator_ai",
        )

    def review(
        self,
        job: Dict[str, Any],
        master: Dict[str, Any],
        plan: Dict[str, Any],
        draft: Dict[str, Any],
    ) -> Dict[str, Any]:
        deterministic = review_cv_rules(job, master, plan, draft)
        result = _agent_call(
            self.client,
            "cv_quality_checker",
            REVIEWER_PROMPT,
            {
                "annonce_complete": job,
                "source_verite": _truth_context(master),
                "plan_adaptation": plan,
                "cv_a_juger": draft,
                "controle_python": deterministic,
            },
        )
        return _merge_review(result.data, deterministic, result)

    def revise(
        self,
        job: Dict[str, Any],
        master: Dict[str, Any],
        plan: Dict[str, Any],
        draft: Dict[str, Any],
        review: Dict[str, Any],
    ) -> Dict[str, Any]:
        result = _agent_call(
            self.client,
            "cv_style_reviser",
            REVISER_PROMPT,
            {
                "annonce_complete": job,
                "source_verite": _truth_context(master),
                "plan_adaptation": plan,
                "brouillon": draft,
                "jugement": review,
            },
        )
        final = _sanitize_cv_content(
            result.data,
            job,
            master,
            plan,
            draft,
            result,
            "cv_style_reviser_ai",
        )
        final["source_draft_agent"] = draft.get("agent")
        final["review_applied"] = {
            "initial_quality_score": review.get("quality_score"),
            "initial_ats_score": review.get("ats_score"),
            "status_before_revision": review.get("status"),
            "problem_count": len(review.get("problems", [])),
        }
        return final
