"""Client for the private subscription-CLI bridge shared with Coolify."""

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


class CLIBridgeError(RuntimeError):
    """Raised when the private CLI bridge cannot return a JSON object."""


@dataclass(frozen=True)
class CLIBridgeResult:
    data: Dict[str, Any]
    provider: str
    model: str


class CLIAgentBridgeClient:
    def __init__(
        self,
        *,
        socket_path: str | None = None,
        token: str | None = None,
        token_file: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.socket_path = socket_path or os.getenv(
            "CV_CLI_BRIDGE_SOCKET",
            "/app/data/.cv_cli_bridge.sock",
        )
        provider_timeout = float(os.getenv("CV_CLI_BRIDGE_TIMEOUT_SECONDS", "300"))
        self.timeout = (
            timeout
            if timeout is not None
            else float(
                os.getenv("CV_CLI_BRIDGE_CLIENT_TIMEOUT_SECONDS", str(provider_timeout * 2 + 30))
            )
        )
        self.token = (token or os.getenv("CV_CLI_BRIDGE_TOKEN", "")).strip()
        if not self.token:
            path = Path(
                token_file
                or os.getenv(
                    "CV_CLI_BRIDGE_TOKEN_FILE",
                    "/app/data/.cv_cli_bridge_token",
                )
            )
            try:
                self.token = path.read_text(encoding="utf-8").strip()
            except OSError:
                self.token = ""

    def complete_json(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        payload: Dict[str, Any],
        preferred_provider: str | None = None,
    ) -> CLIBridgeResult:
        if not self.token:
            raise CLIBridgeError("Jeton du bridge CLI absent")
        request = {
            "operation": "complete_json",
            "token": self.token,
            "agent_name": agent_name,
            "system_prompt": system_prompt,
            "payload": payload,
        }
        if preferred_provider:
            request["preferred_provider"] = preferred_provider
        encoded = (
            json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            + b"\n"
        )
        if len(encoded) > 1_500_000:
            raise CLIBridgeError("La requête du bridge CLI dépasse la taille autorisée")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(self.timeout)
                connection.connect(self.socket_path)
                connection.sendall(encoded)
                response_line = connection.makefile("rb").readline(2_000_001)
        except (OSError, TimeoutError) as exc:
            raise CLIBridgeError(f"Bridge CLI indisponible: {exc}") from exc
        if not response_line or len(response_line) > 2_000_000:
            raise CLIBridgeError("Réponse vide ou trop volumineuse du bridge CLI")
        try:
            response = json.loads(response_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CLIBridgeError("Réponse invalide du bridge CLI") from exc
        if not response.get("ok"):
            detail = response.get("detail") or response.get("error") or "erreur inconnue"
            raise CLIBridgeError(f"Bridge CLI: {detail}")
        data = response.get("data")
        if not isinstance(data, dict):
            raise CLIBridgeError("Le bridge CLI n'a pas renvoyé d'objet JSON")
        return CLIBridgeResult(
            data=data,
            provider=str(response.get("provider") or "cli_bridge"),
            model=str(response.get("model") or "subscription-default"),
        )
