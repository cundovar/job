"""Une seule lecture de l'annonce, partagée par la lettre et le CV.

La préparation d'une candidature lance l'agent analyste une fois et range son
plan dans ``<dossier>/cv/offer_analysis.json``. La chaîne CV le relit au lieu
de relire l'annonce, tant que l'annonce et les consignes du candidat n'ont
pas changé (empreinte). Sans plan réutilisable, elle refait l'analyse comme
avant : le fichier est une économie, jamais une condition.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict

from .ai_agents import AICVPipeline, AgentClient, CVAgentError
from .cv_truth_validator import with_candidate_statements

_LOG = logging.getLogger(__name__)

ANALYSIS_FILE = "offer_analysis.json"


def offer_fingerprint(job: Dict[str, Any]) -> str:
    """Empreinte de ce que l'analyste a lu : l'annonce et les consignes du candidat."""
    payload = json.dumps(
        {
            "description": str(job.get("description") or ""),
            "consignes": str(job.get("candidate_instructions") or ""),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def analyze_offer(
    job: Dict[str, Any],
    master: Dict[str, Any],
    llm_client: AgentClient | None = None,
) -> Dict[str, Any] | None:
    """Plan de l'agent analyste, ou ``None`` s'il n'a pas pu lire l'annonce.

    Un échec n'arrête pas la préparation : la lettre retombe sur la sélection
    par mots-clés, et la chaîne CV refera sa propre analyse.
    """
    enriched = with_candidate_statements(master, job.get("candidate_instructions"))
    try:
        return AICVPipeline(llm_client).analyze(job, enriched)
    except CVAgentError as exc:
        _LOG.warning("Analyse de l'annonce impossible, repli sur les mots-clés : %s", exc)
        return None


def save_offer_analysis(application_dir: str | Path, job: Dict[str, Any], plan: Dict[str, Any]) -> Path:
    target = Path(application_dir) / "cv" / ANALYSIS_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"fingerprint": offer_fingerprint(job), "plan": plan}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def load_offer_analysis(application_dir: str | Path, job: Dict[str, Any]) -> Dict[str, Any] | None:
    """Le plan enregistré, s'il porte encore sur cette annonce et ces consignes."""
    path = Path(application_dir) / "cv" / ANALYSIS_FILE
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(stored, dict) or stored.get("fingerprint") != offer_fingerprint(job):
        return None
    plan = stored.get("plan")
    return plan if isinstance(plan, dict) and plan.get("experience_plan") else None
