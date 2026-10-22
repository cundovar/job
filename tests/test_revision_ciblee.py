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


# ── Compétence affichée sans preuve (cas « Python », D2P 22/10/2026) ─────────

from cv_generator.cv_truth_validator import _validate_skill_evidence

PLAN_PREUVES = {"priority_keywords": ["agents IA et MCP", "Python"], "evidence_matches": [
    {"requirement": "agents IA", "matched_terms": ["agents IA", "Python"], "project_ids": ["pipeline"], "experience_ids": []},
    {"requirement": "MCP", "matched_terms": ["MCP"], "project_ids": ["devdoc_mcp"], "experience_ids": []},
]}


def _cv(projects, skills, bullets=()):
    return {
        "skills": [{"title": "IA", "items": skills}],
        "projects": [{"id": pid, "title": pid, "description": "", "technologies": []} for pid in projects],
        "experiences": [{"id": "a", "bullets": list(bullets)}],
    }


def test_competence_sans_preuve_visible_localisee():
    issues = _validate_skill_evidence(_cv(["devdoc_mcp"], ["MCP", "Python"]), PLAN_PREUVES)
    assert [(i.code, i.path) for i in issues] == [("SKILL_SHOWN_WITHOUT_EVIDENCE", "skills[0].items[1]")]
    assert issues[0].kind == "format"


def test_competence_prouvee_par_projet_visible_ou_nommee_dans_une_puce():
    assert _validate_skill_evidence(_cv(["pipeline"], ["Python"]), PLAN_PREUVES) == []
    assert _validate_skill_evidence(_cv([], ["Python"], [{"text": "Scripts Python d'automatisation."}]), PLAN_PREUVES) == []


def test_competence_hors_plan_non_jugee():
    assert _validate_skill_evidence(_cv([], ["Docker"]), PLAN_PREUVES) == []


def test_le_patch_peut_retirer_la_competence_signalee():
    from cv_generator.ai_patch import _parse_patch_path

    flat = {"skills": [{"title": "IA", "items": ["MCP", "Python"]}]}
    out = _apply_cv_patch(flat, [{"action": "remove", "path": "skills[0].items[1]"}],
                          [_parse_patch_path("skills[0].items[1]")])
    assert out["skills"][0]["items"] == ["MCP"]


def test_titre_mesure_dans_la_vraie_mise_en_page():
    from cv_generator.cv_pdf_design import title_line_count

    assert title_line_count("Formateur IA & conception de supports pédagogiques") == 1
    assert title_line_count(" ".join(["Formateur"] * 40)) > 2


def test_competence_secondaire_non_jugee():
    plan = dict(PLAN_PREUVES, priority_keywords=["MCP"])
    assert _validate_skill_evidence(_cv(["devdoc_mcp"], ["MCP", "Python"]), plan) == []


# ── Vérificateur : chaque puce collée à ses preuves (faux refus D2P) ─────────

def test_chaque_puce_porte_ses_preuves_et_leur_texte():
    from cv_generator.ai_plan import with_cited_evidence

    master = {
        "experience_catalog": {"q": {"highlights": ["Contribution à une plateforme SaaS.", "x", "PHPStan, PHPCS, PHPUnit."]}},
        "candidate_statements": ["J'ai aussi animé des ateliers CV."],
        "project_catalog": {"devdoc": {"description": "Pages de cours, exercices de code, QCM."}},
    }
    cv = {"experiences": [{"id": "q", "bullets": ["Plateforme SaaS ; qualité PHPStan.", "Ateliers CV."],
                           "bullet_sources": [["q:0", "q:2"], ["consignes_candidat:0"]]}],
          "projects": [{"id": "devdoc"}]}
    view = with_cited_evidence(cv, master)
    first, second = view["experiences"][0]["bullets"]
    assert [p["ref"] for p in first["preuves_citees"]] == ["q:0", "q:2"]
    assert first["preuves_citees"][1]["texte"] == "PHPStan, PHPCS, PHPUnit."
    assert second["preuves_citees"][0]["texte"].startswith("J'ai aussi")
    assert "bullet_sources" not in view["experiences"][0]
    assert cv["experiences"][0]["bullets"][0] == "Plateforme SaaS ; qualité PHPStan."   # original intact
