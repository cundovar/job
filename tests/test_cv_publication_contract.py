"""Le contrat de publication : qui a le droit d'appeler un CV « prêt ».

Deux moitiés doivent dire la même chose — le pipeline Python, qui écrit (ou
n'écrit pas) les fichiers finaux, et le serveur Node, qui décide de les servir.
Ces tests vérifient les deux, et qu'elles concordent.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESOLVER = PROJECT_ROOT / "server" / "services" / "cvPublication.js"

FINAL_FILES = (
    "cv_final.json",
    "cv_final.html",
    "cv_final.pdf",
    "cv_ats.html",
    "cv_ats.pdf",
)
PREVIEW_FILES = (
    "cv_review_preview.html",
    "cv_review_preview.pdf",
    "cv_review_preview_ats.pdf",
)
DIAGNOSTIC_FILES = (
    "cv_content.json",
    "cv_truth_check.json",
    "cv_final_review.json",
    "cv_assessment.json",
    "cv_agent_trace.json",
)

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="Node absent : le résolveur JS n'est pas exécutable."
)


def resolve(files, assessment=None, review=None):
    """Exécute la règle Node telle quelle, sans la réécrire en Python."""
    payload = json.dumps(
        {"files": files, "assessment": assessment, "review": review}, ensure_ascii=False
    )
    script = (
        f"import {{ resolveCvPublication }} from {json.dumps(RESOLVER.as_uri())};"
        f"const input = {payload};"
        "process.stdout.write(JSON.stringify("
        "resolveCvPublication(input.files, input.assessment, input.review)));"
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def files_map(present):
    return {name: name in present for name in (*FINAL_FILES, *PREVIEW_FILES, *DIAGNOSTIC_FILES)}


def assessment(status, *, blocking=(), formats=(), rounds=0):
    return {
        "overall_status": status,
        "publication": {
            "revision_rounds": rounds,
            "revision_limit": 3,
            "blocking_issues": list(blocking),
            "format_issues": list(formats),
        },
    }


# --------------------------------------------------------------------------- #
# La règle de publication côté serveur
# --------------------------------------------------------------------------- #


def test_a_dossier_without_any_cv_stays_optional():
    """Sans CV généré, rien n'est bloqué : le CV reste facultatif."""
    result = resolve(files_map(()))

    assert result["status"] == "absent"
    assert result["revision_rounds"] is None


def test_ready_requires_both_the_verdict_and_the_files():
    result = resolve(files_map(FINAL_FILES + DIAGNOSTIC_FILES), assessment("ready"))

    assert result["status"] == "ready"
    assert result["reason"] is None


def test_a_ready_verdict_without_final_files_is_not_ready():
    """On ne propose jamais au téléchargement un fichier qui n'existe pas."""
    result = resolve(files_map(DIAGNOSTIC_FILES + PREVIEW_FILES), assessment("ready"))

    assert result["status"] == "review"
    assert "absents ou incomplets" in result["reason"]


def test_review_reports_the_judge_verdict():
    result = resolve(
        files_map(DIAGNOSTIC_FILES + PREVIEW_FILES),
        assessment("review", formats=[{"code": "BULLET_TOO_LONG", "detail": "Puce trop longue."}]),
        {"status": "needs_revision", "verdict": "Une preuve centrale manque."},
    )

    assert result["status"] == "review"
    assert result["reason"] == "Une preuve centrale manque."
    assert result["format_issues"][0]["code"] == "BULLET_TOO_LONG"


def test_review_falls_back_on_the_format_issue_when_the_judge_is_silent():
    result = resolve(
        files_map(DIAGNOSTIC_FILES + PREVIEW_FILES),
        assessment("review", formats=[{"code": "BULLET_TOO_LONG", "detail": "Puce trop longue."}]),
        {"status": "validated"},
    )

    assert result["reason"] == "Puce trop longue."


def test_blocked_names_the_failing_truth_control():
    result = resolve(
        files_map(DIAGNOSTIC_FILES + PREVIEW_FILES),
        assessment(
            "blocked",
            blocking=[{"code": "BULLET_WITHOUT_SOURCE", "detail": "Aucune preuve citée."}],
            rounds=3,
        ),
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "Aucune preuve citée."
    assert result["revision_rounds"] == 3


def test_a_legacy_dossier_is_never_read_as_ready():
    """Un dossier antérieur au contrat n'a pas d'évaluation lisible : prudence."""
    result = resolve(files_map(FINAL_FILES), None)

    assert result["status"] == "review"
    assert "antérieur au contrat" in result["reason"]


def test_a_corrupt_assessment_is_never_read_as_ready():
    result = resolve(files_map(FINAL_FILES), {"overall_status": None})

    assert result["status"] == "review"


# --------------------------------------------------------------------------- #
# Ce que le pipeline écrit réellement sur disque
# --------------------------------------------------------------------------- #


@pytest.fixture()
def careco(tmp_path):
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "careco_cv_case.json").read_text(encoding="utf-8")
    )
    master = tmp_path / "master.json"
    master.write_text(json.dumps(fixture["master"], ensure_ascii=False), encoding="utf-8")
    return fixture, master


def test_a_ready_run_and_the_server_agree(tmp_path, careco):
    """Le pipeline publie, et le serveur le confirme sur les mêmes fichiers."""
    from cv_generator import prepare_custom_cv
    from test_cv_generator import CarecoAgentClient

    fixture, master = careco
    dossier = tmp_path / "dossier"
    result = prepare_custom_cv(
        fixture["job"],
        application_dir=dossier,
        master_path=master,
        llm_client=CarecoAgentClient(),
    )

    assert result["published"] is True
    present = {path.name for path in (dossier / "cv").iterdir()}
    assert set(FINAL_FILES) <= present

    served = resolve(
        {name: name in present for name in (*FINAL_FILES, *PREVIEW_FILES, *DIAGNOSTIC_FILES)},
        json.loads((dossier / "cv" / "cv_assessment.json").read_text(encoding="utf-8")),
        json.loads((dossier / "cv" / "cv_final_review.json").read_text(encoding="utf-8")),
    )
    assert served["status"] == "ready"


def test_a_refused_run_and_the_server_agree(tmp_path, careco):
    """Le pipeline ne publie pas, et le serveur refuse de servir un final."""
    from cv_generator import prepare_custom_cv
    from test_cv_generator import InventingAgentClient

    fixture, master = careco
    dossier = tmp_path / "dossier"
    result = prepare_custom_cv(
        fixture["job"],
        application_dir=dossier,
        master_path=master,
        llm_client=InventingAgentClient(),
    )

    assert result["published"] is False
    present = {path.name for path in (dossier / "cv").iterdir()}
    assert not set(FINAL_FILES) & present
    assert "cv_review_preview.pdf" in present
    assert set(DIAGNOSTIC_FILES) <= present

    served = resolve(
        {name: name in present for name in (*FINAL_FILES, *PREVIEW_FILES, *DIAGNOSTIC_FILES)},
        json.loads((dossier / "cv" / "cv_assessment.json").read_text(encoding="utf-8")),
        json.loads((dossier / "cv" / "cv_final_review.json").read_text(encoding="utf-8")),
    )
    assert served["status"] == "blocked"
    assert served["blocking_issues"]


def test_the_server_file_allowlist_covers_what_the_pipeline_writes(tmp_path, careco):
    """Aucun artefact produit n'est hors de la liste blanche de téléchargement."""
    from cv_generator import prepare_custom_cv
    from test_cv_generator import CarecoAgentClient

    fixture, master = careco
    dossier = tmp_path / "dossier"
    prepare_custom_cv(
        fixture["job"],
        application_dir=dossier,
        master_path=master,
        llm_client=CarecoAgentClient(),
    )

    script = (
        f"import {{ CV_FILES }} from {json.dumps(RESOLVER.as_uri())};"
        "process.stdout.write(JSON.stringify([...CV_FILES]));"
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        timeout=60,
    )
    allowed = set(json.loads(completed.stdout))
    produced = {path.name for path in (dossier / "cv").iterdir()}

    assert produced <= allowed, produced - allowed
