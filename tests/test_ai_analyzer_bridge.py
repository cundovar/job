from analyzers.ai_analyzer import AIAnalyzer
from utils.cli_agent_bridge import CLIBridgeResult


class FakeBridgeClient:
    def __init__(self):
        self.calls = []

    def complete_json(self, *, agent_name, system_prompt, payload, preferred_provider=None):
        self.calls.append(
            {
                "agent_name": agent_name,
                "system_prompt": system_prompt,
                "payload": payload,
                "preferred_provider": preferred_provider,
            }
        )
        return CLIBridgeResult(
            data={
                "pertinence_score": 88,
                "recommandation": "POSTULER",
                "raison_breve": "Annonce cohérente avec le profil.",
            },
            provider="codex_cli",
            model="subscription-default",
        )


def test_ai_analyzer_uses_subscription_cli_bridge_first(monkeypatch):
    monkeypatch.setenv("JOB_AI_PROVIDER_ORDER", "codex_cli")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    bridge = FakeBridgeClient()
    analyzer = AIAnalyzer(bridge_client=bridge)
    job = {
        "title": "Développeur full stack Symfony Vue.js",
        "company": "Entreprise Test",
        "location": "Paris",
        "contract_type": "CDI",
        "description": "Symfony, Vue.js, API et accompagnement des utilisateurs. " * 8,
        "score": 82,
    }
    criteria = {
        "user_profile": {
            "target_roles": ["Développeur full stack", "Webmaster", "Formateur web"],
            "skills": ["Symfony", "Vue.js", "WordPress"],
        }
    }

    result = analyzer.analyze_job(job, criteria)

    assert result["recommandation"] == "POSTULER"
    assert len(bridge.calls) == 1
    call = bridge.calls[0]
    assert call["agent_name"] == "job_offer_analyzer"
    assert call["payload"]["candidate_profile"] == criteria["user_profile"]
    assert call["payload"]["job_offer"]["title"] == job["title"]
    assert len(call["payload"]["job_offer"]["description"]) <= 2500
    assert call["preferred_provider"] == "codex"


def test_ai_analyzer_keeps_python_immediate_pass_filter(monkeypatch):
    monkeypatch.setenv("JOB_AI_PROVIDER_ORDER", "cli")
    bridge = FakeBridgeClient()
    analyzer = AIAnalyzer(bridge_client=bridge)
    job = {
        "title": "Senior Java Developer",
        "description": "Java backend sans PHP ni JavaScript. " * 20,
    }

    result = analyzer.analyze_job(job, {"user_profile": {}})

    assert result["recommandation"] == "PASSER"
    assert bridge.calls == []
