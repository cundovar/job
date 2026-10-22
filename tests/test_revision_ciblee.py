"""Révision ciblée : une remarque grave du juge est obligatoire et réparable.

Cas réel (D2P Paris 1, 22/10/2026) : le juge demandait de changer un projet et
le titre, mais la remarque partait « facultative » et hors du périmètre du
patch. Le CV finissait « à corriger » après trois tours inutiles.
"""
import pytest

from cv_generator.ai_agents import AgentResult
from cv_generator.ai_assembly import _merge_review, _review_path, build_correction_contract
from cv_generator.ai_patch import _apply_cv_patch, _patch_scope
from cv_generator.ai_client import CVAgentError

RUN = AgentResult({}, "injected", "test")


@pytest.mark.parametrize("value, expected", [
    ("projects[1]", "projects[1]"),
    ("title", "title"),
    ("experiences[2].bullets", "experiences[2].bullets"),
    ("Compétences « IA » + bloc Projets", ""),
    ("contact", ""),
    ("experiences[0].bullet_sources[0][1]", ""),
])
def test_chemin_de_remarque(value, expected):
    assert _review_path(value) == expected


def _review(*problems):
    return _merge_review({"status": "needs_revision", "problems": list(problems)}, {}, RUN, {})


def test_remarque_grave_obligatoire_et_dans_le_perimetre():
    review = _review(
        {"code": "PLAN_NON_COMPLIANCE", "severity": "high", "section": "Projets", "path": "projects[1]",
         "problem": "Projet hors plan.", "suggested_fix": "Remettre devdoc_course_mcp."},
        {"code": "LINK_DUPLICATION", "severity": "low", "section": "Pôle S", "path": "experiences[1]",
         "problem": "Lien répété."},
        {"code": "SOURCE_GAP", "severity": "high", "section": "Moodle", "problem": "Moodle absent."},
    )
    contract = build_correction_contract(review)
    by_code = {item["code"]: item for item in contract}
    assert by_code["PLAN_NON_COMPLIANCE"]["blocking"] is True
    assert by_code["LINK_DUPLICATION"]["blocking"] is False
    assert "SOURCE_GAP" not in by_code                       # jamais au réviseur
    assert [("projects", 1)] in _patch_scope(contract)


def test_le_cosmetique_seul_ne_bloque_plus():
    assert _review({"severity": "low", "section": "x", "path": "experiences[0]", "problem": "Une puce de plus."})["status"] == "validated"
    assert _review({"severity": "medium", "section": "x", "path": "title", "problem": "Titre générique."})["status"] == "needs_revision"


FLAT = {
    "title": "Formateur IA",
    "profile": "Accroche.",
    "skills": [{"title": "IA", "items": ["MCP"]}],
    "experiences": [{"id": "a", "bullets": [{"text": "Un.", "sources": ["a:0"]}]}],
    "projects": [{"id": "p1"}, {"id": "p2"}],
    "education": [],
}


def test_patch_titre_projet_et_ajout_de_puce():
    scope = [[("title", None)], [("projects", None)], [("experiences", 0)]]
    out = _apply_cv_patch(FLAT, [
        {"action": "modify", "path": "title", "new": "Formateur IA & ingénierie pédagogique"},
        {"action": "modify", "path": "projects[1]", "new": {"id": "p3"}},
        {"action": "add", "path": "experiences[0].bullets", "new": {"text": "Deux.", "sources": ["a:1"]}},
    ], scope)
    assert out["title"].endswith("pédagogique")
    assert [p["id"] for p in out["projects"]] == ["p1", "p3"]
    assert len(out["experiences"][0]["bullets"]) == 2
    assert FLAT["projects"][1] == {"id": "p2"}               # le brouillon n'est pas modifié


def test_ajout_sans_preuve_ou_hors_perimetre_refuse():
    with pytest.raises(CVAgentError, match="preuve"):
        _apply_cv_patch(FLAT, [{"action": "add", "path": "experiences[0].bullets", "new": {"text": "x"}}],
                        [[("experiences", 0)]])
    with pytest.raises(CVAgentError, match="hors périmètre"):
        _apply_cv_patch(FLAT, [{"action": "modify", "path": "title", "new": "x"}], [[("projects", None)]])
