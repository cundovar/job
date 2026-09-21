"""Orchestration de la chaîne CV : agents décideurs, Python arbitre de publication."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .ai_agents import (
    AICVPipeline,
    AgentClient,
    CVAgentError,
    build_correction_contract,
    correction_fingerprint,
)
from .ats_exporter import cv_to_ats_html, cv_to_ats_pdf
from .ats_validator import validate_ats_pdf
from .cv_assessment import build_cv_assessment
from .exporters import cv_to_html, cv_to_pdf
from .utils import load_json, save_json

#: Trois passes de correction au maximum : assez pour réparer, trop peu pour
#: boucler indéfiniment sur un désaccord que l'IA ne sait pas résoudre.
MAX_AUTOMATIC_REVISION_ROUNDS = 3
#: Seuls ces verdicts du juge déclenchent un tour de révision. Une demande
#: « mineure » ne vaut pas trois appels IA : elle reste consignée dans
#: `final_ai_review` et le CV est publié (cf. `_apply_final_review_status`).
REVISION_STATUSES = {"needs_revision"}

#: Artefacts réservés à un CV réellement accepté.
FINAL_ARTEFACTS = ("cv_final.html", "cv_final.pdf", "cv_ats.html", "cv_ats.pdf")
#: Artefacts produits quand le CV reste en révision, nommés sans ambiguïté.
PREVIEW_ARTEFACTS = (
    "cv_review_preview.html",
    "cv_review_preview.pdf",
    "cv_review_preview_ats.html",
    "cv_review_preview_ats.pdf",
)


#: Colonne vertébrale de la construction, dans l'ordre. La révision n'y figure
#: pas : elle boucle sur les étapes 3 et 4 et se compte à part.
PROGRESS_STEPS = (
    ("analysis", "Analyse de l'annonce et du profil"),
    ("writing", "Rédaction du CV par l'agent"),
    ("verification", "Vérification des preuves citées"),
    ("judgement", "Jugement de pertinence et ATS"),
    ("export", "Mise en page et export"),
)

PROGRESS_FILE = "cv_progress.json"


def _write_progress(
    output_dir: Path,
    step: str,
    *,
    detail: str = "",
    revision_round: int = 0,
    status: str | None = None,
) -> None:
    """Publie l'étape courante pour que l'interface suive la construction.

    Le pipeline tourne dans un sous-processus : ce fichier est le seul moyen
    pour le serveur de savoir où en est la chaîne, plutôt que de n'afficher
    qu'un « en cours » indifférencié.
    """
    labels = dict(PROGRESS_STEPS)
    order = [name for name, _ in PROGRESS_STEPS]
    save_json(
        output_dir / PROGRESS_FILE,
        {
            "step": step,
            "label": labels.get(step, "Terminé" if step == "done" else step),
            "detail": detail,
            "index": order.index(step) + 1 if step in order else len(order),
            "total": len(order),
            "revision_round": revision_round,
            "revision_limit": MAX_AUTOMATIC_REVISION_ROUNDS,
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def _trace_item(payload: Dict[str, Any]) -> Dict[str, Any]:
    item = {
        "agent": payload.get("agent"),
        **(payload.get("agent_run") or {}),
    }
    if "evidence_coverage" in payload:
        item["evidence_coverage"] = payload.get("evidence_coverage")
    if "verdict" in payload and payload.get("agent") == "cv_truth_checker_ai":
        item["truth_verdict"] = payload.get("verdict")
    return item


def _apply_final_review_status(assessment: Dict[str, Any], final_review: Dict[str, Any]) -> Dict[str, Any]:
    assessment["final_ai_review"] = {
        "status": final_review.get("status"),
        "quality_score": final_review.get("quality_score"),
        "ats_score": final_review.get("ats_score"),
        "verdict": final_review.get("verdict"),
        "evidence_coverage": final_review.get("evidence_coverage", []),
    }
    # L'avis IA peut retarder un CV prêt, jamais débloquer un contrôle en échec.
    if final_review.get("status") == "needs_revision" and assessment["overall_status"] == "ready":
        assessment["overall_status"] = "review"
    return assessment


def _remove_stale(output_dir: Path, names: tuple[str, ...]) -> List[str]:
    """Retire les artefacts d'un run précédent devenus faux.

    Un `cv_final.pdf` laissé derrière décrirait un contenu que le pipeline
    vient de refuser : le garder au nom de la prudence reviendrait à offrir un
    CV périmé au téléchargement.
    """
    removed = []
    for name in names:
        path = output_dir / name
        if path.exists():
            path.unlink()
            removed.append(name)
    return removed


def _finish_without_content(
    job: Dict[str, Any],
    plan: Dict[str, Any],
    output_dir: Path,
    application_dir: str | Path,
    stage: str,
    error: str,
) -> Dict[str, Any]:
    """Termine proprement quand le rédacteur n'a rien produit d'exploitable."""
    assessment = _contract_violation_assessment(stage, error)
    assessment["publication"] = {
        "revision_rounds": 0,
        "revision_limit": MAX_AUTOMATIC_REVISION_ROUNDS,
        "stopped_because": "agent_contract_violation",
        "truth_verdict": None,
        "agent_error": error,
        "blocking_issues": [],
        "format_issues": [],
    }
    trace = {
        "pipeline": "ai_cv_pipeline_v4",
        "job": {"title": job.get("title"), "company": job.get("company"), "url": job.get("url")},
        "runs": [_trace_item(plan)],
        "rounds": [],
        "correction_retried": False,
        "automatic_revision_rounds": 0,
        "automatic_corrections_exhausted": True,
        "automatic_revision_limit": MAX_AUTOMATIC_REVISION_ROUNDS,
        "stopped_because": "agent_contract_violation",
        "agent_error": error,
        "published": False,
        "stale_artefacts_removed": _remove_stale(
            output_dir, FINAL_ARTEFACTS + ("cv_final.json",)
        ),
    }
    save_json(output_dir / "cv_adaptation_plan.json", plan)
    save_json(output_dir / "cv_agent_trace.json", trace)
    save_json(output_dir / "cv_assessment.json", assessment)
    _write_progress(output_dir, "done", detail=error, status="review")
    return {
        "ok": True,
        "pipeline": trace["pipeline"],
        "application_dir": str(Path(application_dir)),
        "cv_dir": str(output_dir),
        "selected_base_variant": plan.get("selected_base_variant"),
        "target_title": plan.get("target_title"),
        "quality_score": 0,
        "ats_score": 0,
        "status": "review",
        "published": False,
        "assessment": assessment,
        "agent_runs": trace["runs"],
        "files": {
            "plan": str(output_dir / "cv_adaptation_plan.json"),
            "agent_trace": str(output_dir / "cv_agent_trace.json"),
            "assessment": str(output_dir / "cv_assessment.json"),
        },
    }


def _contract_violation_assessment(stage: str, error: str) -> Dict[str, Any]:
    """Un agent qui viole son contrat produit `review`, jamais un faux échec.

    Aucune dimension n'est mesurable sans contenu : elles restent `review`,
    conformément à la règle « une donnée inconnue ne tranche pas ».
    """
    reason = f"L'agent {stage} n'a pas respecté son contrat : {error}"
    return {
        "schema_version": "cv_assessment_v1",
        "eligibility": {"status": "review", "checks": [], "missing": [], "reason": reason},
        "parseability": {"status": "review", "reason": reason, "missing": ["cv_content"]},
        "match": {"score": 0, "band": "poor", "components": {}},
        "human_quality": {"score": 0, "band": "poor", "components": {}},
        "truthfulness": {
            "status": "review",
            "issues": [],
            "details": [],
            "format_issues": [],
            "reason": reason,
        },
        "overall_status": "review",
    }


def prepare_custom_cv(
    job: Dict[str, Any],
    application_dir: str | Path,
    master_path: str | Path = "data/cv_master_profile.json",
    llm_client: AgentClient | None = None,
) -> Dict[str, Any]:
    """Construit un CV sourcé via cinq rôles IA, sous garde-fous Python non modificatifs."""
    master = load_json(master_path)
    output_dir = Path(application_dir) / "cv"
    output_dir.mkdir(parents=True, exist_ok=True)

    agents = AICVPipeline(llm_client)
    _write_progress(output_dir, "analysis")
    plan = agents.analyze(job, master)

    _write_progress(output_dir, "writing", detail=f"Variante : {plan.get('selected_base_variant')}")
    try:
        draft = agents.create(job, master, plan)
    except CVAgentError as exc:
        # Le rédacteur a violé son contrat : il n'existe aucun contenu à
        # conserver. On écrit malgré tout le plan et le diagnostic, sans quoi
        # le dossier serait invisible et la cause perdue.
        return _finish_without_content(
            job, plan, output_dir, application_dir, "cv_creator_ai", str(exc)
        )

    content = draft
    _write_progress(output_dir, "verification")
    truth_check = agents.verify(job, master, plan, content)
    _write_progress(output_dir, "judgement")
    review = agents.review(job, master, plan, content)
    first_review = review

    trace_runs = [_trace_item(plan), _trace_item(draft), _trace_item(truth_check), _trace_item(review)]
    rounds: List[Dict[str, Any]] = []
    seen_fingerprints = {
        correction_fingerprint(content, build_correction_contract(review, truth_check))
    }
    revision_rounds = 0
    stopped_because = "validated"
    agent_contract_error: str | None = None

    while revision_rounds < MAX_AUTOMATIC_REVISION_ROUNDS:
        blocking = truth_check.get("verdict") == "refused"
        needs_editorial = review.get("status") in REVISION_STATUSES
        if not blocking and not needs_editorial:
            stopped_because = "validated"
            break

        _write_progress(
            output_dir,
            "writing",
            detail="Correction des problèmes relevés",
            revision_round=revision_rounds + 1,
        )
        try:
            revised = agents.revise(job, master, plan, content, review, truth_check)
            _write_progress(
                output_dir, "verification", revision_round=revision_rounds + 1
            )
            revised_truth = agents.verify(job, master, plan, revised)
            _write_progress(output_dir, "judgement", revision_round=revision_rounds + 1)
            revised_review = agents.review(job, master, plan, revised)
        except CVAgentError as exc:
            # Le réviseur a violé son contrat. Le contenu précédent et son
            # diagnostic portent sur le même CV : ils restent valides et
            # publiables en révision. On ne remonte pas un faux échec système.
            agent_contract_error = str(exc)
            stopped_because = "agent_contract_violation"
            break
        # On ne remplace le trio qu'une fois les trois étapes réussies, pour ne
        # jamais associer un contenu neuf à un diagnostic périmé.
        content, truth_check, review = revised, revised_truth, revised_review
        revision_rounds += 1
        trace_runs.extend([_trace_item(content), _trace_item(truth_check), _trace_item(review)])

        corrections = build_correction_contract(review, truth_check)
        rounds.append(
            {
                "round": revision_rounds,
                "truth_verdict": truth_check.get("verdict"),
                "review_status": review.get("status"),
                "blocking_issue_count": len(truth_check.get("truth_issues", [])),
                "format_issue_count": len(truth_check.get("format_issues", [])),
                "relevance_problem_count": len(review.get("problems", [])),
            }
        )
        fingerprint = correction_fingerprint(content, corrections)
        if fingerprint in seen_fingerprints:
            # Le réviseur rend le même contenu avec les mêmes reproches : une
            # passe supplémentaire ne produirait rien de neuf.
            stopped_because = "no_progress"
            break
        seen_fingerprints.add(fingerprint)
    else:
        stopped_because = "revision_limit_reached"

    if stopped_because == "validated" and (
        truth_check.get("verdict") == "refused" or review.get("status") in REVISION_STATUSES
    ):
        stopped_because = "revision_limit_reached"

    blocking_issues = list(truth_check.get("truth_issues", []))
    format_issues = list(truth_check.get("format_issues", []))

    _write_progress(output_dir, "export", revision_round=revision_rounds)
    save_json(output_dir / "cv_adaptation_plan.json", plan)
    save_json(output_dir / "cv_draft.json", draft)
    save_json(output_dir / "cv_review.json", first_review)
    save_json(output_dir / "cv_truth_check.json", truth_check)
    save_json(output_dir / "cv_final_review.json", review)
    save_json(output_dir / "cv_content.json", content)

    # Le PDF ATS sert d'abord à mesurer la lisibilité : on le produit sous un nom
    # d'aperçu, et il ne devient `cv_ats.pdf` que si le CV est publiable.
    preview_ats_pdf = output_dir / "cv_review_preview_ats.pdf"
    (output_dir / "cv_review_preview_ats.html").write_text(
        cv_to_ats_html(content), encoding="utf-8"
    )
    cv_to_ats_pdf(content, preview_ats_pdf)
    parseability = validate_ats_pdf(preview_ats_pdf, content)

    assessment = build_cv_assessment(job, master, plan, content, parseability=parseability)
    assessment = _apply_final_review_status(assessment, review)
    # Un CV que son propre vérificateur refuse n'est jamais « prêt », et une
    # erreur de gabarit non résorbée interdit l'export final.
    if blocking_issues and assessment["overall_status"] != "blocked":
        assessment["overall_status"] = "blocked"
    elif format_issues and assessment["overall_status"] == "ready":
        assessment["overall_status"] = "review"
    if agent_contract_error and assessment["overall_status"] == "ready":
        # Un CV dont la dernière révision a échoué n'est pas « prêt » : la
        # correction demandée n'a jamais été appliquée.
        assessment["overall_status"] = "review"
    assessment["publication"] = {
        "agent_error": agent_contract_error,
        "revision_rounds": revision_rounds,
        "revision_limit": MAX_AUTOMATIC_REVISION_ROUNDS,
        "stopped_because": stopped_because,
        "truth_verdict": truth_check.get("verdict"),
        "blocking_issues": blocking_issues,
        "format_issues": format_issues,
    }

    published = assessment["overall_status"] == "ready"
    files: Dict[str, str] = {
        "plan": str(output_dir / "cv_adaptation_plan.json"),
        "draft": str(output_dir / "cv_draft.json"),
        "review": str(output_dir / "cv_review.json"),
        "truth_check": str(output_dir / "cv_truth_check.json"),
        "final_review": str(output_dir / "cv_final_review.json"),
        "content": str(output_dir / "cv_content.json"),
        "agent_trace": str(output_dir / "cv_agent_trace.json"),
        "assessment": str(output_dir / "cv_assessment.json"),
    }

    if published:
        removed = _remove_stale(output_dir, PREVIEW_ARTEFACTS)
        (output_dir / "cv_final.html").write_text(cv_to_html(content), encoding="utf-8")
        cv_to_pdf(content, output_dir / "cv_final.pdf")
        (output_dir / "cv_ats.html").write_text(cv_to_ats_html(content), encoding="utf-8")
        cv_to_ats_pdf(content, output_dir / "cv_ats.pdf")
        save_json(output_dir / "cv_final.json", content)
        files.update(
            {
                "final_json": str(output_dir / "cv_final.json"),
                "html": str(output_dir / "cv_final.html"),
                "pdf": str(output_dir / "cv_final.pdf"),
                "ats_html": str(output_dir / "cv_ats.html"),
                "ats_pdf": str(output_dir / "cv_ats.pdf"),
            }
        )
    else:
        # Aucun fichier `cv_final` n'est créé ni conservé : ceux d'un run
        # précédent décrivent un contenu qui n'est plus celui retenu.
        removed = _remove_stale(output_dir, FINAL_ARTEFACTS + ("cv_final.json",))
        (output_dir / "cv_review_preview.html").write_text(cv_to_html(content), encoding="utf-8")
        cv_to_pdf(content, output_dir / "cv_review_preview.pdf")
        files.update(
            {
                "preview_html": str(output_dir / "cv_review_preview.html"),
                "preview_pdf": str(output_dir / "cv_review_preview.pdf"),
                "preview_ats_html": str(output_dir / "cv_review_preview_ats.html"),
                "preview_ats_pdf": str(preview_ats_pdf),
            }
        )

    trace = {
        "pipeline": "ai_cv_pipeline_v4",
        "job": {
            "title": job.get("title"),
            "company": job.get("company"),
            "url": job.get("url"),
            "description_chars": len(str(job.get("description") or "")),
            "candidate_instructions_present": bool(
                str(job.get("candidate_instructions") or "").strip()
            ),
            "candidate_instructions_chars": len(
                str(job.get("candidate_instructions") or "").strip()
            ),
        },
        "runs": trace_runs,
        "rounds": rounds,
        "correction_retried": revision_rounds > 0,
        "automatic_revision_rounds": revision_rounds,
        "automatic_corrections_exhausted": stopped_because != "validated",
        "automatic_revision_limit": MAX_AUTOMATIC_REVISION_ROUNDS,
        "stopped_because": stopped_because,
        "agent_error": agent_contract_error,
        "published": published,
        "stale_artefacts_removed": removed,
        "python_guardrails": [
            "identifiants d'expériences limités au JSON maître",
            "intitulés, organisations, dates, diplômes et contacts recopiés depuis la source",
            "chaque puce reliée à une ou plusieurs preuves citées explicitement",
            "compétences, projets et formations vérifiés contre les libellés autorisés",
            "contraintes de gabarit et affirmations interdites signalées, jamais corrigées en silence",
            "artefacts cv_final réservés au statut ready",
        ],
    }
    save_json(output_dir / "cv_agent_trace.json", trace)
    save_json(output_dir / "cv_assessment.json", assessment)
    _write_progress(
        output_dir,
        "done",
        detail=assessment["overall_status"],
        revision_round=revision_rounds,
        status=assessment["overall_status"],
    )

    return {
        "ok": True,
        "pipeline": trace["pipeline"],
        "application_dir": str(Path(application_dir)),
        "cv_dir": str(output_dir),
        "selected_base_variant": plan.get("selected_base_variant"),
        "target_title": content.get("cv", {}).get("title") or plan.get("target_title"),
        "quality_score": assessment["human_quality"]["score"],
        "ats_score": assessment["match"]["score"],
        "status": assessment["overall_status"],
        "published": published,
        "assessment": assessment,
        "agent_runs": trace["runs"],
        "files": files,
    }
