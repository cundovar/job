from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, replace as dataclass_replace
from typing import Any, Dict, Iterable, List, Protocol

from openai import OpenAI

from cv_generator.cv_creator import build_structural_shell
from cv_generator.cv_quality_checker import review_cv as review_cv_rules
from cv_generator.cv_truth_validator import ALLOWED_SECTIONS, validate_cv_content
from cv_generator.job_analyzer import analyze_job_for_cv as analyze_job_rules
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
    duration_seconds: float | None = None


class AgentClient(Protocol):
    def complete_json(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        payload: Dict[str, Any],
    ) -> AgentResult | Dict[str, Any]: ...


BUDGET_HINT = (
    "Relever CV_AI_MAX_TOKENS : un modèle de raisonnement dépense ce budget en "
    "réflexion avant d'écrire sa réponse."
)


def _check_completion(content: str, finish_reason: str | None, max_tokens: int) -> str:
    """Traduit une réponse vide en cause lisible.

    Les modèles de raisonnement consomment le budget de complétion avant
    d'émettre le moindre caractère. Quand il est trop court, l'API répond
    `finish_reason="length"` avec un contenu vide — ce qui, sans ce contrôle,
    remonte en « l'agent n'a pas renvoyé un objet JSON » et envoie chercher un
    bug de parsing là où il n'y a qu'un budget insuffisant.
    """
    if finish_reason == "length":
        # Une réponse coupée en plein JSON est inutilisable même si elle n'est
        # pas vide : la laisser passer produisait plus loin une erreur de
        # contrat trompeuse, très loin de la vraie cause.
        raise CVAgentError(
            f"budget de complétion épuisé "
            f"({'avant émission de contenu' if not content.strip() else f'après {len(content)} caractères'}, "
            f"max_tokens={max_tokens}, finish_reason=length). " + BUDGET_HINT
        )
    if content.strip():
        return content
    raise CVAgentError(
        f"réponse vide du fournisseur (finish_reason={finish_reason or 'inconnu'})"
    )


def _parse_json_response(content: str) -> Dict[str, Any]:
    raw = (content or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Un JSON qui ne se referme pas est une réponse tronquée. Tenter de
        # sauver un préfixe donnerait un objet amputé de ses dernières clés, et
        # l'erreur remonterait comme une violation de contrat de l'agent.
        if raw and not raw.rstrip().endswith("}"):
            raise CVAgentError(
                f"réponse tronquée : le JSON ne se referme pas "
                f"({len(raw)} caractères reçus). " + BUDGET_HINT
            )
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
        # 60 s ne suffit pas au budget de tokens ci-dessous : le modèle passe
        # plusieurs minutes à raisonner avant de répondre.
        timeout = float(os.getenv("CV_AI_TIMEOUT_SECONDS", os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "300")))
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
        glm_key = os.getenv("GLM_API_KEY")
        self._glm = (
            OpenAI(
                api_key=glm_key,
                base_url=os.getenv("GLM_BASE_URL", "https://api.z.ai/api/paas/v4"),
                timeout=timeout,
            )
            if glm_key
            else None
        )
        self._glm_model = os.getenv("CV_GLM_MODEL", os.getenv("GLM_MODEL", "glm-5.3"))
        self._claude_model = os.getenv("CV_CLAUDE_MODEL", "claude-sonnet-4-6")
        self._temperature = float(os.getenv("CV_AI_TEMPERATURE", "0.2"))
        # 5000 ne suffit pas : cv_job_analyzer dépense à lui seul ~12 200 tokens
        # de raisonnement avant d'émettre un caractère, et la réponse revient vide.
        self._max_tokens = int(os.getenv("CV_AI_MAX_TOKENS", "32000"))
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
        choice = response.choices[0]
        content = _check_completion(
            choice.message.content or "", choice.finish_reason, self._max_tokens
        )
        return AgentResult(_parse_json_response(content), "deepseek", selected_model)

    def _call_glm(
        self,
        system_prompt: str,
        user_message: str,
        model: str | None = None,
    ) -> AgentResult:
        if self._glm is None:
            raise CVAgentError("GLM_API_KEY absente")
        selected_model = model or self._glm_model
        response = self._glm.chat.completions.create(
            model=selected_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        choice = response.choices[0]
        content = _check_completion(
            choice.message.content or "", choice.finish_reason, self._max_tokens
        )
        return AgentResult(_parse_json_response(content), "glm", selected_model)

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
        # Anthropic dit "max_tokens" là où l'API OpenAI dit "length".
        finish_reason = "length" if response.stop_reason == "max_tokens" else response.stop_reason
        content = _check_completion(content, finish_reason, self._max_tokens)
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
                if provider == "glm":
                    return self._call_glm(system_prompt, user_message, step.model)
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
La préanalyse Python est purement consultative: aucun de ses éléments n'est imposé. Python ne
réinjectera aucune expérience que tu écartes et n'imposera aucun nombre minimum. Tu as la
responsabilité entière de la sélection, de l'ordre et du regroupement.
Les consignes_candidat sont des préférences éditoriales prioritaires, séparées de l'annonce.
Respecte-les lorsqu'elles sont réalisables avec la source de vérité. Si elles demandent une
affirmation absente, contradictoire ou interdite, refuse cette partie et ajoute un avertissement.
N'inclus une expérience que si elle apporte une preuve explicite à un critère de l'annonce.
Il est préférable de retenir moins d'expériences plutôt que de remplir les emplacements avec
des expériences faibles ou hors sujet. Respecte la visibilité conditionnelle de la source.
Quand l'annonce combine formation, développement web et IA, couvre trois piliers avec des
preuves distinctes: pédagogie auprès du public visé, réalisation technique réelle et pratique
de l'IA. Recherche aussi une réalisation publique pertinente quand la source fournit un lien.
Choisis librement les meilleures preuves: aucun identifiant d'expérience n'est obligatoire.
Préférence permanente du candidat: pour toute variante de formateur, conserve l'expérience
mairie_chelles comme preuve humaine complémentaire d'animation, de projets pédagogiques et de
travail avec des groupes. Cette préférence vient du candidat, pas d'une décision Python.

JSON attendu:
{
  "selected_base_variant": "id existant",
  "target_title": "titre du CV",
  "positioning": "accroche proposée",
  "priority_keywords": ["..."],
  "experience_plan": [
    {"experience_id":"...","priority":10,"reason":"...","highlight_indexes":[0,1]}
  ],
  "critical_requirements":[{"requirement":"...","importance":"high"}],
  "evidence_matches":[{"requirement":"...","evidence_id":"id existant","project_ids":["..."]}],
  "presentation_strategy":{"experience_display_mode":"individual|grouped_missions","experience_group_id":"id de experience_groups","member_ids":["ids présents dans experience_plan"]},
  "section_order":["profile","skills","projects","experiences","education"],
  "selected_projects":["id projet existant"],
  "skills_to_emphasize": {"nom_section":["compétence exacte de la source"]},
  "skills_to_reduce": ["..."],
  "warnings": ["..."]
}
""".strip()


def _standing_preference_clause(master, plan, role: str) -> str:
    """Consigne injectee uniquement si la variante retenue a une preference permanente."""
    variant = (plan or {}).get("selected_base_variant")
    preferences = (
        (master or {})
        .get("adaptation_rules", {})
        .get("standing_experience_preferences_by_variant", {})
        .get(variant)
        or []
    )
    if not preferences:
        return ""
    ids = ", ".join(str(item) for item in preferences)
    if role == "creator":
        return (
            f"\nPour cette variante, respecte la preference permanente d'inclure {ids} en fin de "
            "parcours comme preuve humaine complementaire, sans lui faire remplacer une preuve "
            "metier centrale."
        )
    return (
        f"\nPour cette variante, human_group_facilitation doit etre couvert par {ids}, "
        "conformement a la preference permanente du candidat."
    )


CREATOR_PROMPT = """
Tu es l'agent rédacteur du CV. Rédige un CV ciblé et crédible en français à partir du plan,
du brouillon structurel et de la source de vérité. Tu peux reformuler une preuve, mais pas
ajouter de mission, résultat, chiffre, outil, niveau, date ou diplôme absent de la source.
Tu décides seul du contenu final. Python ne complète rien: une expérience que tu omets restera
absente, une puce que tu n'écris pas ne sera pas fabriquée, et l'ordre que tu donnes est celui
qui sera rendu. Sélectionne, omets et réordonne librement expériences, compétences, projets et
formations, à condition que chaque élément existe dans la source de vérité.
Applique les consignes_candidat comme préférences éditoriales prioritaires. Elles ne peuvent
jamais autoriser une expérience, une compétence ou un niveau absent de la source de vérité.
Présente les expériences retenues dans un ordre antéchronologique cohérent. Utilise
skills_confidence pour ne jamais présenter des bases ou notions comme une maîtrise solide.
Pour une annonce large de développement web, conserve une stack projet représentative de
plusieurs couches pertinentes plutôt qu'une technologie isolée. Ne prétends jamais avoir animé
des formations en ligne ou à distance sans preuve explicite dans la source de vérité.
Les intitulés d'expériences ne sont jamais réécrits. Chaque puce doit citer ses preuves dans
"sources", au format "experience_id:index_du_highlight" (ou "project_id"). Une puce sans source
est refusée. Une puce d'un bloc groupé ne peut citer que les missions de son groupe. Les compétences doivent reprendre exactement un libellé autorisé.
Respecte la presentation_strategy et section_order du plan. Quand grouped_missions est demandé,
écris directement UN SEUL bloc portant l'identifiant du groupe, avec "source_experience_ids" et
autant de puces que nécessaire pour conserver les preuves de CHAQUE mission du groupe. Le moteur
ne regroupe plus à ta place: si tu n'écris qu'une puce, une seule preuve subsistera. Pour une annonce IA, rends visibles les projets qui prouvent Python, MCP,
l'orchestration et les boucles de contrôle. N'écris pas « profil transférable » et n'utilise pas
« bases en Python » dans l'accroche : montre le niveau réel par les réalisations disponibles.
Respecte strictement les limites Canva fournies: une longueur dépassée est renvoyée en correction,
elle n'est plus tronquée automatiquement.

JSON attendu:
{
  "title":"...",
  "profile":"...",
  "skills":[{"title":"...","items":["libellé exact"]}],
  "experiences":[
    {"id":"experience_id","bullets":[{"text":"...","sources":["experience_id:0"]}]},
    {"id":"group_id","source_experience_ids":["mission_a","mission_b"],
     "bullets":[{"text":"...","sources":["mission_a:0"]},{"text":"...","sources":["mission_b:1"]}]}
  ],
  "projects":[{"id":"...","description":"reformulation fidèle","technologies":["sous-ensemble exact"]}],
  "education":["intitulé exact présent dans person.education"]
}
""".strip()


TRUTH_CHECKER_PROMPT = """
Tu es l'agent vérificateur de vérité. Ton seul rôle est d'accepter ou de refuser des
affirmations sourcées. Tu ne juges ni la pertinence, ni le style, ni l'adéquation à l'annonce :
un autre agent s'en charge. Tu ne proposes aucune reformulation et tu ne réécris rien.
Pour chaque puce du CV, compare son texte aux highlights cités dans ses sources et à la source
de vérité. Une puce est `supported` si son contenu découle directement des preuves citées.
Elle est `unsupported` si elle ajoute un fait, un chiffre, un outil, un niveau, une date, un
client ou un résultat que les preuves citées ne contiennent pas — même si l'information est
vraie ailleurs dans la source de vérité : la preuve citée doit être la bonne.
Vérifie de la même façon l'accroche, le titre, les compétences affichées et les descriptions
de projets. Le contrôle Python joint liste déjà les références introuvables : tu traites ce que
Python ne peut pas voir, c'est-à-dire l'écart de sens entre une preuve et sa reformulation.
Sois strict : dans le doute, `unsupported`, en expliquant précisément ce qui manque.

JSON attendu:
{
  "verdict":"accepted|refused",
  "claims":[
    {"path":"experiences[0].bullets[1]","source_refs":["exp_id:0"],"status":"supported|unsupported",
     "reason":"ce que la preuve citée ne dit pas"}
  ],
  "summary":"..."
}
""".strip()


REVIEWER_PROMPT = """
Tu es l'agent juge du CV. Sois sévère et factuel. Compare l'annonce, le CV, le plan et la
source de vérité. Évalue: adéquation réelle, mots-clés ATS, absence d'invention, respect des
intitulés, crédibilité du niveau, clarté, concision et contraintes Canva. Une compétence de
l'annonce absente du profil est un écart, pas une compétence à ajouter. Signale précisément
chaque problème et propose une correction fondée sur la source. Tu es responsable du verdict,
du score qualité et du score ATS. Le contrôle Python joint sert uniquement à signaler les
erreurs factuelles ou techniques; il ne décide pas de la pertinence éditoriale.
Vérifie aussi que les consignes_candidat réalisables ont été respectées. Signale précisément
toute consigne oubliée, mais ne pénalise pas le CV pour une demande impossible ou non sourcée.
Pour une annonce hybride de formation web et IA, renseigne les cinq piliers de couverture.
Chaque preuve doit citer uniquement un identifiant d'expérience ou de projet existant dans la
source. Un pilier manquant doit produire une correction concrète et influencer ton verdict.\nVérifie que les expériences sont présentées dans un ordre antéchronologique et signale toute\ninversion. Pour chaque exigence critique du plan, vérifie qu'une expérience ou un projet visible\napporte une preuve. Une technologie demandée mais absente de la source est un écart honnête non réparable :
ne la classe pas en sévérité haute et ne déclenche pas une révision à elle seule. Utilise le code
SKILL_WITHOUT_EVIDENCE lorsqu'une compétence importante est\naffichée ou demandée sans preuve concrète visible dans le CV.

JSON attendu:
{
  "strengths":["..."],
  "problems":[{"code":"SKILL_WITHOUT_EVIDENCE|autre_code","severity":"high|medium|low","section":"...","problem":"...","suggested_fix":"..."}],
  "missing_keywords":["..."],
  "overrepresented_keywords":["..."],
  "forbidden_claims_found":["..."],
  "evidence_coverage":[
    {
      "pillar":"pedagogy|technical_delivery|ai_practice|public_proof|human_group_facilitation",
      "status":"covered|partial|missing|not_applicable",
      "experience_ids":["id exact"],
      "project_ids":["id exact"],
      "gap":"preuve manquante ou vide"
    }
  ],
  "quality_score": 0,
  "ats_score": 0,
  "status":"validated|needs_minor_revision|needs_revision",
  "verdict":"..."
}
""".strip()


REVISER_PROMPT = """
Tu es l'agent réviseur final. Applique les corrections du juge sans inventer et sans modifier
les vrais intitulés d'expérience. Préserve la provenance de chaque puce dans "sources", au format
"experience_id:index" ou "project_id". Une puce sans source est refusée. N'ajoute que des compétences dont le libellé exact existe dans la source.
Tu peux ajouter, retirer ou réordonner tout élément sourcé; aucune sélection Python n'est
obligatoire. Le jugement IA décide de la pertinence, Python ne contrôle que la vérité et le format.
Applique les consignes_candidat et les corrections du juge ensemble. Si une consigne contredit
la source de vérité ou exige une invention, ignore seulement cette partie et reste factuel.
Respecte les niveaux de skills_confidence et l'ordre antéchronologique. Une exigence de l'annonce
absente de la source reste un écart honnête; elle ne doit jamais être transformée en compétence.
Utilise evidence_coverage du jugement pour combler chaque pilier partiel ou manquant avec les
meilleures preuves disponibles, sans forcer un identifiant particulier. Priorise les corrections
SKILL_WITHOUT_EVIDENCE : ajoute une preuve sourcée visible ou retire la compétence insuffisamment
étayée. Préserve presentation_strategy et section_order du plan.
Respecte les limites Canva: un dépassement de longueur est une correction à appliquer, Python ne
tronque plus. Corrige aussi chaque erreur listée dans controle_python: une erreur de vérité
interdit la publication, une erreur de format doit disparaître avant l'export.
Retourne EXACTEMENT la même forme que `brouillon` : un objet à plat avec title, profile, skills,
experiences, projects et education à la racine. N'imbrique jamais ta réponse sous une clé "cv".
Chaque puce garde la forme {text, sources}, un bloc groupé garde source_experience_ids et une
puce par mission, projects garde un sous-ensemble de technologies exactes, et education les
intitulés exacts.
""".strip()


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
            "location": person.get("location"),
            "languages": person.get("languages", []),
            "education": person.get("education", []),
            "eligibility": person.get("eligibility", {}),
        },
        "skills_confidence": master.get("skills_confidence", {}),
        "experience_catalog": master.get("experience_catalog", {}),
        "project_catalog": master.get("project_catalog", {}),
        "evidence_catalog": master.get("evidence_catalog", {}),
        "experience_groups": master.get("experience_groups", {}),
        "layout_constraints": master.get("layout_constraints", {}),
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
    if variant_id not in variants:
        variant_id = str(rule_plan.get("selected_base_variant") or next(iter(variants), "webmaster"))
    catalog = master.get("experience_catalog", {})

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
        if exp_id in seen:
            continue
        if exp_id not in catalog:
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
    if not experience_plan:
        raise CVAgentError(
            "Aucune expérience proposée par l'agent analyste n'existe dans le profil "
            f"maître (reçu : {', '.join(unknown) or 'rien'})."
        )

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
    }


def _validate_presentation_strategy(
    proposed: Any,
    variant_id: str,
    planned_ids: Iterable[str],
    master: Dict[str, Any],
) -> Dict[str, Any]:
    """Accepte le regroupement demandé par l'agent s'il est déclaré et cohérent.

    Python ne décide plus de grouper : il refuse un groupe impossible et laisse
    l'agent seul juge de l'opportunité de le faire.
    """
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
            links: List[str] = []
            for member in member_ids:
                for link in catalog.get(member, {}).get("links", []):
                    if link not in links:
                        links.append(link)
            entry = {
                "id": exp_id,
                "source_experience_ids": member_ids,
                "selection_role": "core",
                "organization": " · ".join(
                    organization for organization in dict.fromkeys(organizations) if organization
                ),
                "title": group.get("title", "Missions et projets professionnels"),
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
                "title": source.get("title", ""),
                "period": period_to_text(source.get("period")),
                "bullets": bullets,
                "bullet_sources": bullet_sources,
                "links": source.get("links", [])[:2],
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
                "links": source.get("links", [])[:2],
            }
        )

    education_catalog = {
        normalize(entry.get("title")): entry
        for entry in master.get("person", {}).get("education", [])
        if isinstance(entry, dict) and normalize(entry.get("title"))
    }
    education: List[Dict[str, Any]] = []
    for item in proposed.get("education") or []:
        title = item.get("title") if isinstance(item, dict) else item
        entry = education_catalog.get(normalize(title))
        education.append(entry if entry is not None else {"title": str(title)})

    person = master.get("person", {})
    variant_id = str(plan.get("selected_base_variant") or "")
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
    ai_reported_high = any(item.get("severity") == "high" for item in problems)
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


_PATCH_MODE_PROMPT = """
Privilégie le mode patch : réponds exactement {"changes": [{"action": "modify"|"remove",
"path": "<chemin>", "new": <nouvelle valeur>}]}, un changement par correction à appliquer.
Chemins acceptés : "profile", "skills[k].items[m]", "experiences[i]",
"experiences[i].bullets[j]", "projects[i]", "education[i]". Ne cible que les location
listées dans corrections_a_appliquer : tout ce qui n'est pas visé reste inchangé, ne renvoie
pas le CV complet. Une puce modifiée exige {"text": "...", "sources": ["experience_id:index"
ou "project_id"]} avec ses preuves. Si le patch ne suffit vraiment pas, renvoie le schéma
complet du rédacteur.
""".strip()


def _parse_patch_path(path: Any) -> List[Any]:
    """« experiences[1].bullets[2] » → [("experiences", 1), ("bullets", 2)]."""
    tokens: List[Any] = []
    for part in str(path or "").split("."):
        match = re.fullmatch(r"([a-z_]+)(?:\[(\d+)\])?", part.strip())
        if not match:
            raise CVAgentError(f"Chemin de patch invalide : « {path} ».")
        name, index = match.group(1), match.group(2)
        tokens.append((name, int(index) if index is not None else None))
    if not tokens:
        raise CVAgentError("Chemin de patch vide.")
    return tokens


def _patch_scope(contract: List[Dict[str, Any]]) -> List[List[Any]]:
    """Les préfixes de chemins que le patch a le droit de toucher.

    Seules les erreurs bloquantes — vérité et gabarit — définissent le
    périmètre : un patch n'existe pas pour aller retoucher du cosmétique.
    La valeur « cv » (affirmation interdite sans localisation fine) ouvre tout.
    """
    prefixes: List[List[Any]] = []
    for item in contract or []:
        if item.get("origin") not in {"truth", "format"}:
            continue
        location = item.get("location")
        if not location:
            continue
        try:
            prefixes.append(_parse_patch_path(location))
        except CVAgentError:
            continue
    return prefixes


def _patch_token_matches(prefix_token: Any, path_token: Any) -> bool:
    """Un segment de contrat couvre-t-il un segment de chemin ?

    Un contrat sans index — « experiences » pour `TOO_MANY_EXPERIENCES`,
    « skills » pour `TOO_MANY_SKILL_SECTIONS` — porte sur la liste entière :
    il ouvre donc chacun de ses éléments, sans quoi la seule correction
    possible (retirer l'élément de trop) serait refusée comme hors périmètre.
    """
    name, index = prefix_token
    other_name, other_index = path_token
    if name != other_name:
        return False
    return index is None or index == other_index


def _patch_path_in_scope(tokens: List[Any], prefixes: List[List[Any]]) -> bool:
    for prefix in prefixes:
        if prefix and prefix[0] == ("cv", None):
            return True
        if len(tokens) < len(prefix):
            continue
        if all(
            _patch_token_matches(prefix_token, path_token)
            for prefix_token, path_token in zip(prefix, tokens)
        ):
            return True
    return False


def _patch_parent(flat: Dict[str, Any], tokens: List[Any]) -> Any:
    """Navigue vers le parent du dernier token ; renvoie (conteneur, clé)."""
    node: Any = flat
    for name, index in tokens[:-1]:
        if index is None:
            if not isinstance(node, dict) or name not in node:
                raise CVAgentError(f"Chemin de patch introuvable : « {name} ».")
            node = node[name]
        else:
            if not isinstance(node, dict) or name not in node:
                raise CVAgentError(f"Chemin de patch introuvable : « {name} ».")
            container = node[name]
            if not isinstance(container, list) or index >= len(container):
                raise CVAgentError(f"Index de patch hors limites : « {name}[{index}] ».")
            node = container[index]
    name, index = tokens[-1]
    if index is None:
        if not isinstance(node, dict):
            raise CVAgentError(f"Chemin de patch invalide pour la cible « {name} ».")
        return node, name
    if not isinstance(node, dict) or name not in node:
        raise CVAgentError(f"Chemin de patch introuvable : « {name} ».")
    container = node[name]
    if not isinstance(container, list) or index >= len(container):
        raise CVAgentError(f"Index de patch hors limites : « {name}[{index}] ».")
    return container, index


def _apply_cv_patch(
    flat: Dict[str, Any],
    changes: Any,
    scope: List[List[Any]],
) -> Dict[str, Any]:
    """Applique les changements du réviseur aux seuls chemins ciblés.

    Python est un exécuteur mécanique : il pose la valeur rendue par l'agent
    à l'endroit demandé et ne touche à rien d'autre — le reste du CV reste
    identique octet pour octet au brouillon entrant.
    """
    if not isinstance(changes, list) or not changes:
        raise CVAgentError("Patch vide : la liste « changes » est absente ou vide.")

    # Lecture complète avant la moindre écriture : un patch dont un seul
    # changement est illisible ou hors périmètre est refusé en bloc, jamais
    # appliqué à moitié.
    lus: List[Any] = []
    for change in changes:
        if not isinstance(change, dict):
            raise CVAgentError("Changement de patch illisible (élément non objet).")
        action = str(change.get("action") or "").strip().lower()
        if action not in {"modify", "remove"}:
            raise CVAgentError(
                f"Action de patch inconnue : « {change.get('action')} »."
            )
        tokens = _parse_patch_path(change.get("path"))
        if not _patch_path_in_scope(tokens, scope):
            raise CVAgentError(
                f"Chemin de patch hors périmètre du contrat : « {change.get('path')} »."
            )
        lus.append((action, tokens, change))

    # Les index d'un patch désignent tous le brouillon *entrant*. Une
    # suppression appliquée trop tôt décale la liste, et la correction
    # suivante atterrit sur la puce voisine — texte de l'agent posé sur la
    # mauvaise preuve, sans que le validateur puisse le voir. On modifie
    # donc d'abord, à index stables, puis on supprime du dernier au premier.
    modifications = [item for item in lus if item[0] == "modify"]
    suppressions = sorted(
        (item for item in lus if item[0] == "remove"),
        key=lambda item: tuple(
            (name, -1 if index is None else index) for name, index in item[1]
        ),
        reverse=True,
    )

    updated = copy.deepcopy(flat)
    for _, tokens, change in modifications:
        container, key = _patch_parent(updated, tokens)
        new = change.get("new")
        container[key] = new
        # Une puce réécrite doit rester sourcée : on refuse tout de suite ce
        # que le validateur bloquerait plus tard, avec la localisation.
        if tokens[-1][0] == "bullets" and tokens[-1][1] is not None:
            if not isinstance(new, dict) or not str(new.get("text") or "").strip():
                raise CVAgentError(
                    f"Puce modifiée sans texte : « {change.get('path')} »."
                )
            if not isinstance(new.get("sources"), list) or not new["sources"]:
                raise CVAgentError(
                    f"Puce modifiée sans preuve citée : « {change.get('path')} »."
                )

    for _, tokens, change in suppressions:
        container, key = _patch_parent(updated, tokens)
        if not isinstance(container, list):
            raise CVAgentError(
                f"« remove » ne s'applique pas à « {change.get('path')} »."
            )
        del container[key]

    return updated


def _wrap_patched_cv(
    draft: Dict[str, Any],
    flat: Dict[str, Any],
    job: Dict[str, Any],
    master: Dict[str, Any],
    plan: Dict[str, Any],
    result: AgentResult,
) -> Dict[str, Any]:
    """Réassemble le CV autour du contenu patché.

    Le flat patché est au schéma rédacteur (puces {text, sources}) : on le
    repasse dans l'assemblage déterministe — mêmes identifiants, donc mêmes
    intitulés et mêmes preuves pour tout ce que le patch n'a pas touché. La
    sortie reste byte-identique au brouillon hors chemins ciblés.
    """
    final = _assemble_cv_content(
        flat,
        job,
        master,
        plan,
        result,
        "cv_style_reviser_ai",
    )
    final["source_draft_agent"] = draft.get("agent")
    return final


class AICVPipeline:
    def __init__(self, client: AgentClient | None = None) -> None:
        self.client = client or CVLLMClient()
        #: Échecs de patch consécutifs du réviseur : à 2, on cesse de lui
        #: proposer le mode patch et on repasse en réécriture complète.
        self._patch_failures = 0

    def analyze(self, job: Dict[str, Any], master: Dict[str, Any]) -> Dict[str, Any]:
        rule_plan = analyze_job_rules(job, master)
        result = _agent_call(
            self.client,
            "cv_job_analyzer",
            ANALYZER_PROMPT,
            {
                "annonce_complete": _announcement_context(job),
                "consignes_candidat": _candidate_instructions(job),
                "source_verite": _truth_context(master, "analyzer"),
                "preanalyse_python": rule_plan,
            },
        )
        return _validate_plan(result.data, rule_plan, master, result)

    def create(
        self,
        job: Dict[str, Any],
        master: Dict[str, Any],
        plan: Dict[str, Any],
    ) -> Dict[str, Any]:
        result = _agent_call(
            self.client,
            "cv_creator",
            CREATOR_PROMPT + _standing_preference_clause(master, plan, "creator"),
            {
                "annonce_complete": _announcement_context(job),
                "consignes_candidat": _candidate_instructions(job),
                "source_verite": _truth_context(master, "creator"),
                "plan_adaptation": plan,
                # Le squelette ne porte que ce qui n'est pas éditorial : contact,
                # localisation, langues et contraintes de gabarit.
                "squelette_structurel": build_structural_shell(
                    master, str(plan.get("selected_base_variant") or "")
                ),
            },
        )
        return _assemble_cv_content(
            result.data,
            job,
            master,
            plan,
            result,
            "cv_creator_ai",
        )

    def verify(
        self,
        job: Dict[str, Any],
        master: Dict[str, Any],
        plan: Dict[str, Any],
        draft: Dict[str, Any],
        previous_content: Dict[str, Any] | None = None,
        previous_truth: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Contrôle la vérité avant tout jugement éditorial.

        Python passe en premier : une référence introuvable n'a pas besoin d'un
        appel IA pour être refusée. L'agent n'est consulté que sur ce que Python
        ne peut pas voir — l'écart de sens entre une preuve et sa reformulation.

        Après une révision, le contrôle devient ciblé : Python diff le contenu
        validé et le contenu révisé, l'agent ne re-juge que les chemins
        modifiés, les chemins intacts gardent leur verdict précédent. Si rien
        n'a bougé, aucun appel IA n'est dépensé du tout.
        """
        validation = validate_cv_content(draft, master, plan)
        previous_claims: List[Dict[str, Any]] | None = None
        changed_paths: List[str] = []
        if previous_content is not None and previous_truth is not None:
            changed_paths = _cv_diff_paths(
                previous_content.get("cv", {}), draft.get("cv", {})
            )
            previous_claims = [
                item for item in previous_truth.get("claims") or [] if isinstance(item, dict)
            ]
            if not changed_paths:
                # Rien n'a bougé : le verdict précédent reste exact. Python
                # re-valide tout le CV (gratuit), l'agent n'est pas rappelé.
                previous_run = previous_truth.get("agent_run") or {}
                inherited = AgentResult(
                    data={},
                    provider=str(previous_run.get("provider") or "injected"),
                    model=str(previous_run.get("model") or "injected"),
                    duration_seconds=0.0,
                )
                merged = _merge_truth_check(
                    {"claims": previous_claims},
                    validation,
                    inherited,
                    previous_claims=previous_claims,
                    changed_paths=[],
                )
                merged["agent_run"]["reused"] = True
                return merged

        payload = {
            "source_verite": _truth_context(master, "reviewer"),
            "cv_a_verifier": draft.get("cv", {}),
            "controle_python": validation["issues"],
        }
        if previous_claims is not None and changed_paths:
            payload["verification_ciblee"] = {
                "consigne": (
                    "Seuls les chemins listés dans chemins_modifies ont changé depuis la "
                    "validation précédente : concentre l'analyse de sens sur eux, en rendant "
                    "un claim par chemin modifié. Les chemins intacts listés dans "
                    "statuts_deja_valides portent exactement le même texte qu'au tour "
                    "précédent où ils ont été jugés : ne les re-analyse pas, leur statut "
                    "antérieur sera conservé tel quel."
                ),
                "chemins_modifies": changed_paths[:60],
                "statuts_deja_valides": [
                    {"path": item.get("path"), "status": item.get("status")}
                    for item in previous_claims
                    if not _claim_affected(str(item.get("path") or ""), changed_paths)
                ][:80],
            }
        result = _agent_call(
            self.client,
            "cv_truth_checker",
            TRUTH_CHECKER_PROMPT,
            payload,
        )
        return _merge_truth_check(
            result.data,
            validation,
            result,
            previous_claims=previous_claims,
            changed_paths=changed_paths or None,
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
            REVIEWER_PROMPT + _standing_preference_clause(master, plan, "reviewer"),
            {
                "annonce_complete": _announcement_context(job),
                "consignes_candidat": _candidate_instructions(job),
                "source_verite": _truth_context(master, "reviewer"),
                "plan_adaptation": plan,
                "cv_a_juger": draft,
                "controle_python": deterministic,
            },
        )
        return _merge_review(result.data, deterministic, result, master)

    def revise(
        self,
        job: Dict[str, Any],
        master: Dict[str, Any],
        plan: Dict[str, Any],
        draft: Dict[str, Any],
        review: Dict[str, Any],
        truth_check: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        contract = build_correction_contract(review, truth_check)
        payload = {
            "annonce_complete": _announcement_context(job),
            "consignes_candidat": _candidate_instructions(job),
            "source_verite": _truth_context(master, "reviser"),
            "plan_adaptation": plan,
            "brouillon": to_writer_schema(draft),
            "jugement": review,
            "corrections_a_appliquer": contract,
        }

        # Mode patch : le réviseur ne rend que les chemins à corriger, Python
        # applique mécaniquement — le reste du CV reste identique au brouillon,
        # aucune partie validée ne peut régresser. Après deux échecs de patch
        # consécutifs, repli durable sur la réécriture complète.
        final = None
        if getattr(self, "_patch_failures", 0) < 2:
            scope = _patch_scope(contract)
            if scope:
                result = _agent_call(
                    self.client,
                    "cv_style_reviser",
                    REVISER_PROMPT + "\n\n" + _PATCH_MODE_PROMPT,
                    payload,
                )
                data = result.data
                if isinstance(data, dict) and isinstance(data.get("changes"), list):
                    try:
                        flat = _apply_cv_patch(payload["brouillon"], data["changes"], scope)
                    except CVAgentError as patch_error:
                        # Le patch est refusé : l'erreur localisée part avec le
                        # contrat de l'appel de repli, sans quoi le réviseur
                        # réécrirait à l'aveugle la cause de son propre échec.
                        self._patch_failures = getattr(self, "_patch_failures", 0) + 1
                        contract = contract + [
                            {
                                "origin": "patch",
                                "blocking": True,
                                "code": "PATCH_REFUSE",
                                "location": None,
                                "problem": str(patch_error),
                                "suggested_fix": (
                                    "Renvoie cette fois le schéma complet du rédacteur."
                                ),
                            }
                        ]
                        payload["corrections_a_appliquer"] = contract
                    else:
                        self._patch_failures = 0
                        final = _wrap_patched_cv(
                            draft, flat, job, master, plan, result
                        )
                elif isinstance(data, dict) and data.get("experiences"):
                    # Le modèle a rendu le schéma complet malgré la consigne
                    # patch : chemin historique, toléré sans compter un échec.
                    final = _assemble_cv_content(
                        data,
                        job,
                        master,
                        plan,
                        result,
                        "cv_style_reviser_ai",
                    )
                else:
                    # Ni patch ni schéma complet : échec de patch, le repli
                    # ci-dessous referme le tour.
                    self._patch_failures = getattr(self, "_patch_failures", 0) + 1
                    contract = contract + [
                        {
                            "origin": "patch",
                            "blocking": True,
                            "code": "PATCH_ILLISIBLE",
                            "location": None,
                            "problem": (
                                "La réponse précédente n'était ni un patch « changes » "
                                "ni le schéma complet du rédacteur."
                            ),
                            "suggested_fix": "Renvoie le schéma complet du rédacteur.",
                        }
                    ]
                    payload["corrections_a_appliquer"] = contract

        if final is None:
            result = _agent_call(
                self.client,
                "cv_style_reviser",
                REVISER_PROMPT,
                payload,
            )
            final = _assemble_cv_content(
                result.data,
                job,
                master,
                plan,
                result,
                "cv_style_reviser_ai",
            )
        # Dernier passage obligatoire : quelle que soit la voie (patch ciblé ou
        # réécriture complète), la section compétences repasse par la liste
        # blanche du profil maître avant de sortir de la révision.
        final["skills"] = _filter_skills_whitelist(final.get("skills"), master)
        final["source_draft_agent"] = draft.get("agent")
        final["review_applied"] = {
            "initial_quality_score": review.get("quality_score"),
            "initial_ats_score": review.get("ats_score"),
            "status_before_revision": review.get("status"),
            "problem_count": len(review.get("problems", [])),
            "truth_verdict_before_revision": (truth_check or {}).get("verdict"),
        }
        return final
