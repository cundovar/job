"""Client des fournisseurs d'IA de la chaîne CV : routage par rôle, appel, lecture du JSON renvoyé.

Extrait de cv_generator/ai_agents.py, sans changement de comportement.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Protocol

from openai import OpenAI

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
