from types import SimpleNamespace

from cv_generator.ai_agents import CVLLMClient
from utils.ai_role_routing import load_role_route
from utils.cli_agent_bridge import CLIBridgeError


def _route_signature(agent_name):
    return [
        (step.provider, step.model, step.reasoning_effort)
        for step in load_role_route(agent_name)
    ]


def test_role_matrix_matches_approved_provider_order():
    assert _route_signature("job_offer_analyzer") == [
        ("deepseek", "deepseek-v4-flash", None),
        ("codex_cli", "gpt-5.6-sol", "low"),
        ("claude_cli", "sonnet", None),
    ]
    assert _route_signature("cv_job_analyzer") == [
        ("claude_cli", "sonnet", None),
        ("codex_cli", "gpt-5.6-sol", "medium"),
        ("deepseek", "deepseek-v4-flash", None),
    ]
    assert _route_signature("cv_creator") == [
        ("codex_cli", "gpt-5.6-sol", "medium"),
        ("claude_cli", "sonnet", None),
        ("deepseek", "deepseek-v4-flash", None),
    ]
    assert _route_signature("cv_quality_checker") == [
        ("claude_cli", "opus", None),
        ("codex_cli", "gpt-5.6-sol", "high"),
        ("deepseek", "deepseek-v4-flash", None),
    ]
    assert _route_signature("cv_style_reviser") == [
        ("codex_cli", "gpt-5.6-sol", "medium"),
        ("claude_cli", "sonnet", None),
        ("deepseek", "deepseek-v4-flash", None),
    ]
    assert _route_signature("agent_redacteur_lettres") == [
        ("claude_cli", "opus", None),
        ("codex_cli", "gpt-5.6-sol", "medium"),
        ("deepseek", "deepseek-v4-flash", None),
    ]


def test_model_names_can_be_overridden_without_code_changes(monkeypatch):
    monkeypatch.setenv("AI_CLAUDE_OPUS_MODEL", "claude-opus-5")
    monkeypatch.setenv("AI_CODEX_SOL_MODEL", "codex-sol-test")

    judge = load_role_route("cv_quality_checker")

    assert judge[0].model == "claude-opus-5"
    assert judge[1].model == "codex-sol-test"


def test_quality_checker_falls_back_from_opus_to_codex(monkeypatch):
    monkeypatch.delenv("CV_AI_PROVIDER_ORDER", raising=False)
    calls = []

    class FallbackBridge:
        def complete_json(
            self,
            *,
            agent_name,
            system_prompt,
            payload,
            preferred_provider=None,
            preferred_model=None,
            reasoning_effort=None,
        ):
            calls.append((preferred_provider, preferred_model, reasoning_effort))
            if preferred_provider == "claude":
                raise CLIBridgeError("Claude indisponible")
            return SimpleNamespace(
                data={"status": "ok"},
                provider="codex_cli",
                model=preferred_model,
            )

    result = CVLLMClient(bridge_client=FallbackBridge()).complete_json(
        agent_name="cv_quality_checker",
        system_prompt="Retourne du JSON.",
        payload={},
    )

    assert result.provider == "codex_cli"
    assert calls == [
        ("claude", "opus", None),
        ("codex", "gpt-5.6-sol", "high"),
    ]
