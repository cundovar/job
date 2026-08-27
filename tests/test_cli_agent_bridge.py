import json
import os
import socket
import stat
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.cv_cli_bridge import CLIAgentBridge, create_server
from utils.cli_agent_bridge import CLIAgentBridgeClient


TOKEN = "test-token-with-more-than-thirty-two-characters"


class FakeProviderBridge:
    provider_order = ["codex", "claude"]

    def __init__(self):
        self.calls = []

    @staticmethod
    def provider_status():
        return {"codex": True, "claude": True}

    def complete_json(
        self,
        agent_name,
        system_prompt,
        payload,
        preferred_provider=None,
        preferred_model=None,
        reasoning_effort=None,
    ):
        self.calls.append(
            {
                "agent_name": agent_name,
                "system_prompt": system_prompt,
                "payload": payload,
                "preferred_provider": preferred_provider,
                "preferred_model": preferred_model,
                "reasoning_effort": reasoning_effort,
            }
        )
        return {
            "data": {"status": "ok"},
            "provider": f"{preferred_provider or 'codex'}_cli",
            "model": "test",
            "duration_seconds": 0.01,
        }


@pytest.fixture
def unix_bridge(tmp_path, monkeypatch):
    monkeypatch.setenv("CV_CLI_BRIDGE_REQUEST_TIMEOUT_SECONDS", "0.15")
    monkeypatch.setenv("CV_CLI_BRIDGE_MAX_CONNECTIONS", "2")
    socket_path = tmp_path / "bridge.sock"
    bridge = FakeProviderBridge()
    server = create_server(socket_path, bridge, TOKEN)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield socket_path, bridge
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        if socket_path.is_socket():
            socket_path.unlink()


def _request(socket_path, payload):
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.settimeout(2)
    try:
        connection.connect(str(socket_path))
        encoded = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            + b"\n"
        )
        connection.sendall(encoded)
        line = connection.makefile("rb").readline()
        return json.loads(line.decode("utf-8"))
    finally:
        connection.close()


def test_unix_bridge_authentication_permissions_and_provider_selection(unix_bridge):
    socket_path, bridge = unix_bridge

    assert stat.S_IMODE(os.stat(socket_path).st_mode) == 0o600
    assert _request(socket_path, {"operation": "health", "token": "wrong"}) == {
        "ok": False,
        "error": "unauthorized",
    }

    response = _request(
        socket_path,
        {
            "operation": "complete_json",
            "token": TOKEN,
            "agent_name": "cv_creator",
            "system_prompt": "Retourne du JSON.",
            "payload": {"job": {"title": "Webmaster"}},
            "preferred_provider": "codex",
            "preferred_model": "gpt-5.6-sol",
            "reasoning_effort": "medium",
        },
    )

    assert response["ok"] is True
    assert response["provider"] == "codex_cli"
    assert bridge.calls[0]["preferred_provider"] == "codex"
    assert bridge.calls[0]["preferred_model"] == "gpt-5.6-sol"
    assert bridge.calls[0]["reasoning_effort"] == "medium"


def test_unix_bridge_rejects_invalid_model_or_reasoning(unix_bridge):
    socket_path, bridge = unix_bridge
    base = {
        "operation": "complete_json",
        "token": TOKEN,
        "agent_name": "cv_creator",
        "system_prompt": "Retourne du JSON.",
        "payload": {},
        "preferred_provider": "codex",
    }

    assert _request(socket_path, {**base, "preferred_model": "bad model --flag"}) == {
        "ok": False,
        "error": "invalid_request",
    }
    assert _request(socket_path, {**base, "reasoning_effort": "ultra"}) == {
        "ok": False,
        "error": "invalid_request",
    }
    assert bridge.calls == []


def test_unix_bridge_rejects_non_object_json(unix_bridge):
    socket_path, _ = unix_bridge
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.settimeout(2)
    try:
        connection.connect(str(socket_path))
        connection.sendall(b"[]\n")
        response = json.loads(connection.makefile("rb").readline().decode("utf-8"))
    finally:
        connection.close()

    assert response == {"ok": False, "error": "invalid_request"}


def test_unix_bridge_times_out_partial_connections(unix_bridge):
    socket_path, _ = unix_bridge
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.settimeout(2)
    try:
        connection.connect(str(socket_path))
        response = json.loads(connection.makefile("rb").readline().decode("utf-8"))
    finally:
        connection.close()

    assert response == {"ok": False, "error": "request_timeout"}


def test_client_timeout_covers_two_provider_attempts(monkeypatch):
    monkeypatch.setenv("CV_CLI_BRIDGE_TIMEOUT_SECONDS", "12")
    monkeypatch.delenv("CV_CLI_BRIDGE_CLIENT_TIMEOUT_SECONDS", raising=False)

    client = CLIAgentBridgeClient(
        socket_path="/tmp/unused.sock",
        token=TOKEN,
    )

    assert client.timeout == 54


def test_cli_commands_apply_requested_model_and_codex_effort(tmp_path, monkeypatch):
    monkeypatch.setenv("CV_CLI_BRIDGE_WORKSPACE", str(tmp_path / "workspace"))
    monkeypatch.setattr("tools.cv_cli_bridge.shutil.which", lambda name: f"/usr/bin/{name}")
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[0].endswith("codex"):
            output_path = Path(command[command.index("--output-last-message") + 1])
            output_path.write_text('{"status":"ok"}', encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout='{\"status\":\"ok\"}', stderr="")

    monkeypatch.setattr("tools.cv_cli_bridge.subprocess.run", fake_run)
    bridge = CLIAgentBridge()

    codex = bridge.complete_json(
        "cv_creator",
        "Retourne du JSON.",
        {},
        preferred_provider="codex",
        preferred_model="gpt-5.6-sol",
        reasoning_effort="medium",
    )
    claude = bridge.complete_json(
        "cv_quality_checker",
        "Retourne du JSON.",
        {},
        preferred_provider="claude",
        preferred_model="opus",
    )

    assert codex["model"] == "gpt-5.6-sol"
    assert "--model" in commands[0] and "gpt-5.6-sol" in commands[0]
    assert 'model_reasoning_effort="medium"' in commands[0]
    assert claude["model"] == "opus"
    assert "--model" in commands[1] and "opus" in commands[1]
