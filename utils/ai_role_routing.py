"""Validated, deterministic AI provider routes keyed by pipeline role."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


DEFAULT_ROUTING_PATH = Path(__file__).resolve().parent.parent / "config" / "ai_role_routing.json"
ALLOWED_PROVIDERS = {"cli", "bridge", "codex_cli", "claude_cli", "deepseek", "claude", "anthropic"}
ALLOWED_REASONING_EFFORTS = {None, "low", "medium", "high"}


@dataclass(frozen=True)
class AIRouteStep:
    provider: str
    model: str | None = None
    reasoning_effort: str | None = None


def _model_value(definition: dict) -> str | None:
    env_name = definition.get("model_env")
    if env_name:
        override = os.getenv(str(env_name), "").strip()
        if override:
            return override
    value = str(definition.get("model") or "").strip()
    return value or None


def load_role_route(
    agent_name: str,
    path: str | Path = DEFAULT_ROUTING_PATH,
) -> List[AIRouteStep]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    models = config.get("models")
    roles = config.get("roles")
    if not isinstance(models, dict) or not isinstance(roles, dict):
        raise ValueError("Configuration de routage IA invalide.")
    route_names = roles.get(agent_name)
    if not isinstance(route_names, list) or not route_names:
        raise ValueError(f"Aucune route IA configurée pour {agent_name}.")

    route: List[AIRouteStep] = []
    for route_name in route_names:
        definition = models.get(route_name)
        if not isinstance(definition, dict):
            raise ValueError(f"Modèle de routage IA inconnu: {route_name}")
        provider = str(definition.get("provider") or "").strip().lower()
        effort = definition.get("reasoning_effort")
        if provider not in ALLOWED_PROVIDERS or effort not in ALLOWED_REASONING_EFFORTS:
            raise ValueError(f"Route IA invalide: {route_name}")
        route.append(
            AIRouteStep(
                provider=provider,
                model=_model_value(definition),
                reasoning_effort=effort,
            )
        )
    return route


def legacy_route(providers: Iterable[str]) -> List[AIRouteStep]:
    route = [AIRouteStep(provider=str(provider).strip().lower()) for provider in providers]
    if not route or any(step.provider not in ALLOWED_PROVIDERS for step in route):
        raise ValueError("Ordre global des fournisseurs IA invalide.")
    return route
