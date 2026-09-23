import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER = PROJECT_ROOT / "hermes_mcp_server.py"


class HermesMCPServerTests(unittest.TestCase):
    def test_job_status_uses_project_data_when_server_started_elsewhere(self):
        cached_jobs = json.loads((PROJECT_ROOT / "data" / "jobs_cache.json").read_text(encoding="utf-8"))
        expected_count = len(cached_jobs)
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "job_status", "arguments": {}},
        }

        with tempfile.TemporaryDirectory() as foreign_cwd:
            completed = subprocess.run(
                [sys.executable, "-u", str(SERVER)],
                input=json.dumps(request) + "\n",
                text=True,
                capture_output=True,
                cwd=foreign_cwd,
                timeout=10,
                check=True,
            )

        response = json.loads(completed.stdout)
        text = response["result"]["content"][0]["text"]
        self.assertIn(f"Offres en cache : {expected_count}", text)


PREPARED_PAYLOAD = {
    "company": "Econovia",
    "title": "Développeur web / Intégrateur",
    "confirmed_findings": 3,
    "recommended_cv": "webmaster",
    "files": {
        "resume": "offre_resume.md",
        "motivation_letter": "lettre_motivation.md",
        "application_email": "mail_candidature.md",
        "metadata": "metadata.json",
    },
}


def test_company_prepare_makes_the_dossier_visible_in_the_front(monkeypatch):
    """Un dossier préparé par Hermes doit arriver dans l'onglet Spontanées.

    Régression : le handler MCP portait sa propre copie de la logique et ne
    reconstruisait pas candidatures.json, contrairement à la CLI. Le dossier
    existait sur le disque mais restait invisible du front — donc invalidable,
    donc inenvoyable. Les deux chemins passent maintenant par la même fonction.
    """
    import hermes_mcp_server
    from hermes_commands import company_prepare

    rebuilt = []
    monkeypatch.setattr(
        hermes_mcp_server, "load_cached_companies", lambda: [{"opportunity": {"title": "Dev"}}]
    )
    monkeypatch.setattr(
        company_prepare, "prepare_application", lambda company, with_cv=True: PREPARED_PAYLOAD
    )
    monkeypatch.setattr(
        company_prepare,
        "rebuild_candidatures_index",
        lambda source, destination: rebuilt.append(Path(destination)),
    )

    text = hermes_mcp_server.TOOLS["company_prepare"]["handler"]({"number": 1})

    assert rebuilt, "candidatures.json n'a pas été reconstruit : le front ne verra rien"
    assert rebuilt[0].name == "candidatures.json"
    assert "Econovia" in text and "Aucun envoi" in text


def test_hermes_has_no_sending_tool():
    """La garantie « Hermes ne peut pas envoyer » tient au code, pas à un prompt."""
    import hermes_mcp_server

    forbidden = [name for name in hermes_mcp_server.TOOLS if "send" in name or "envoi" in name]
    assert forbidden == []


def test_agency_search_refuses_a_scope_less_call():
    """Sans city ni zone explicites, l'ancien défaut « ile-de-france » lançait
    une passe pleine IDF à l'insu de l'appelant : un transport qui perd les
    arguments (schémas MCP vides, incident du 23/09/2026) déclenchait une
    prospection non demandée. Un périmètre se nomme, il ne se déduit plus."""
    import pytest

    import hermes_mcp_server

    with pytest.raises(ValueError, match="Perimetre manquant"):
        hermes_mcp_server.TOOLS["agency_search"]["handler"]({})


def test_job_search_api_url_is_distinct_from_hermes_gateway(monkeypatch):
    """Le MCP appelle Express, jamais le gateway Hermes utilisé par le chat."""
    import hermes_mcp_server

    monkeypatch.setenv("HERMES_API_URL", "http://127.0.0.1:8642")
    monkeypatch.setenv("JOB_SEARCH_API_URL", "http://127.0.0.1:3001/")

    assert hermes_mcp_server._job_search_base_url() == "http://127.0.0.1:3001"


if __name__ == "__main__":
    unittest.main()
