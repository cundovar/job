#!/usr/bin/env python3
"""
Minimal MCP server exposing job-search commands to Hermes.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict

from applications import ApplicationTracker, build_application_package
from hermes_commands.utils import format_job_list, load_cached_jobs, ranked_jobs
from pipeline import run_job_search, load_criteria


def _tool_result(text: str) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _capture(fn: Callable[[], str]) -> Dict[str, Any]:
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stderr(stderr):
            return _tool_result(fn())
    except Exception as exc:
        details = stderr.getvalue().strip()
        message = f"Erreur job-search: {exc}"
        if details:
            message += f"\n\nDetails:\n{details}"
        return {"isError": True, "content": [{"type": "text", "text": message}]}


def job_status(_: Dict[str, Any]) -> str:
    jobs = load_cached_jobs()
    postuler = sum(1 for job in jobs if job.get("ai_analysis", {}).get("recommandation") == "POSTULER")
    peut_etre = sum(1 for job in jobs if job.get("ai_analysis", {}).get("recommandation") == "PEUT-ÊTRE")
    passer = sum(1 for job in jobs if job.get("ai_analysis", {}).get("recommandation") == "PASSER")
    return "\n".join(
        [
            "Statut recherche emploi",
            "",
            f"Offres en cache : {len(jobs)}",
            f"POSTULER : {postuler}",
            f"PEUT-ETRE : {peut_etre}",
            f"PASSER : {passer}",
        ]
    )


def job_top(args: Dict[str, Any]) -> str:
    limit = int(args.get("limit", 5))
    jobs = ranked_jobs(load_cached_jobs(), limit=limit)
    return format_job_list(jobs, title=f"Top {len(jobs)} offres")


def job_today(args: Dict[str, Any]) -> str:
    limit = int(args.get("limit", 5))
    send_outputs = bool(args.get("send_outputs", False))
    result = run_job_search(send_outputs=send_outputs)
    stats = result["stats"]
    top_jobs = ranked_jobs(result["jobs"], limit=limit)
    return "\n".join(
        [
            "Recherche du jour terminee.",
            "",
            f"Offres scrapees : {result['all_jobs_count']}",
            f"Offres filtrees : {stats['total']}",
            f"POSTULER : {stats['postuler']}",
            f"PEUT-ETRE : {stats['peut_etre']}",
            f"PASSER : {stats['passer']}",
            "",
            format_job_list(top_jobs, title=f"Top {len(top_jobs)} offres"),
        ]
    )


def job_prepare(args: Dict[str, Any]) -> str:
    number = int(args.get("number", 1))
    limit = int(args.get("limit", 20))
    jobs = ranked_jobs(load_cached_jobs(), limit=limit)
    if number < 1 or number > len(jobs):
        raise ValueError(f"Offre {number} introuvable. Offres disponibles: {len(jobs)}")
    job = jobs[number - 1]
    criteria = load_criteria()
    package = build_application_package(job, user_profile=criteria.get("user_profile", {}))
    return "\n".join(
        [
            "Candidature preparee.",
            "",
            f"Offre : {job.get('title', 'Poste non renseigne')} - {job.get('company', 'Entreprise non renseignee')}",
            f"Score : {job.get('score', 'Non renseigne')}/100",
            f"Variante CV : {package.recommended_cv.cv_name} ({package.recommended_cv.cv_id})",
            "",
            "Documents generes :",
            f"- {package.resume_path}",
            f"- {package.cv_recommendation_path}",
            f"- {package.motivation_letter_path}",
            f"- {package.application_email_path}",
            f"- {package.metadata_path}",
        ]
    )


def job_relance(args: Dict[str, Any]) -> str:
    tracker_path = str(args.get("tracker", "data/applications_tracker.json"))
    due = ApplicationTracker(tracker_path).due_followups()
    if not due:
        return "Aucune relance a faire aujourd'hui."

    lines = ["Relances a faire", ""]
    for index, record in enumerate(due, start=1):
        lines.extend(
            [
                f"{index}. {record.get('job_title', 'Poste non renseigne')} - {record.get('company', 'Entreprise non renseignee')}",
                f"Postule le : {record.get('applied_at', 'Non renseigne')}",
                f"Relance prevue : {record.get('follow_up_at', 'Non renseignee')}",
                f"URL : {record.get('url', 'Non renseignee')}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


TOOLS: Dict[str, Dict[str, Any]] = {
    "job_status": {
        "description": "Affiche le statut global de la recherche d'emploi.",
        "handler": job_status,
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "job_top": {
        "description": "Affiche les meilleures offres en cache.",
        "handler": job_top,
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 5}},
            "additionalProperties": False,
        },
    },
    "job_today": {
        "description": "Lance la recherche d'emploi du jour.",
        "handler": job_today,
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 5},
                "send_outputs": {"type": "boolean", "default": False},
            },
            "additionalProperties": False,
        },
    },
    "job_prepare": {
        "description": "Prepare une candidature pour une offre du classement.",
        "handler": job_prepare,
        "inputSchema": {
            "type": "object",
            "properties": {
                "number": {"type": "integer", "default": 1},
                "limit": {"type": "integer", "default": 20},
            },
            "additionalProperties": False,
        },
    },
    "job_relance": {
        "description": "Liste les candidatures a relancer aujourd'hui.",
        "handler": job_relance,
        "inputSchema": {
            "type": "object",
            "properties": {"tracker": {"type": "string", "default": "data/applications_tracker.json"}},
            "additionalProperties": False,
        },
    },
}


def _debug(message: str) -> None:
    with open("/tmp/job-search-mcp.log", "a", encoding="utf-8") as f:
        f.write(message + "\n")


def _handle(request: Dict[str, Any]) -> Dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")

    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "job-search", "version": "1.0.0"},
            },
        }
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": name,
                        "description": spec["description"],
                        "inputSchema": spec["inputSchema"],
                    }
                    for name, spec in TOOLS.items()
                ]
            },
        }
    if method == "tools/call":
        params = request.get("params", {})
        name = params.get("name")
        arguments = params.get("arguments", {}) or {}
        if name not in TOOLS:
            result = {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {name}"}]}
        else:
            result = _capture(lambda: TOOLS[name]["handler"](arguments))
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> None:
    os.chdir(Path(__file__).resolve().parent)
    _debug("server-start")
    while True:
        headers = {}
        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                _debug("stdin-eof")
                return
            line = line.decode("utf-8").strip()
            if not line:
                break
            # Support both standard Content-Length framed MCP messages and
            # newline-delimited JSON-RPC messages used by some clients/tests.
            if line.startswith("{"):
                _debug(f"jsonline={line}")
                response = _handle(json.loads(line))
                if response is not None:
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
                    _debug(f"jsonline-response={response.get('id')}")
                headers = {}
                break
            key, _, value = line.partition(":")
            headers[key.lower()] = value.strip()

        _debug(f"headers={headers}")
        content_length = int(headers.get("content-length", "0"))
        if content_length <= 0:
            continue

        body = sys.stdin.buffer.read(content_length).decode("utf-8")
        _debug(f"body={body}")
        response = _handle(json.loads(body))
        if response is not None:
            payload = json.dumps(response).encode("utf-8")
            sys.stdout.buffer.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("utf-8"))
            sys.stdout.buffer.write(payload)
            sys.stdout.buffer.flush()
            _debug(f"response={response.get('id')} {response.get('result', response.get('error'))}")


if __name__ == "__main__":
    main()
