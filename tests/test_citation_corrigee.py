"""Une citation corrigée fait re-juger la puce qu'elle soutient.

Cas réel (Simplon, 23/10/2026) : la puce Qualiopi citait ``pole_s:14`` au lieu
de ``pole_s:13``. Le réviseur a corrigé la citation, mais la vérification
ciblée comparait le chemin modifié (``bullet_sources[2][0]``) au chemin du
refus (``bullets[2]``), ne les reliait pas, et reconduisait l'ancien refus.
Le CV finissait bloqué « faute de progrès » sur une puce déjà réparée. En
prime, la raison coupée à 300 caractères transformait ``pole_s:13`` en
``pole_s:1…``, et le réviseur se voyait suggérer ``pole_s:1``.
"""
from cv_generator.ai_agents import AgentResult
from cv_generator.ai_assembly import _claim_path, _merge_truth_check, _suggested_refs

RUN = AgentResult({}, "injected", "test")
VALIDATION = {"truth_issues": [], "format_issues": [], "source_issues": [], "issues": [], "ok": True, "truthful": True}

REFUS = {
    "path": "experiences[1].bullets[2]",
    "source_refs": ["pole_s:14"],
    "status": "unsupported",
    "reason": "La preuve citée parle de la SIAE.",
}


def test_chemin_de_citation_ramene_sur_la_puce():
    assert _claim_path("experiences[1].bullet_sources[2][0]") == "experiences[1].bullets[2]"
    assert _claim_path("experiences[1].bullet_sources") == "experiences[1].bullets"


def test_citation_corrigee_le_refus_n_est_pas_reconduit():
    nouveau = {"claims": [{**REFUS, "source_refs": ["pole_s:13"], "status": "supported", "reason": "Preuve exacte."}]}
    merged = _merge_truth_check(
        nouveau, VALIDATION, RUN,
        previous_claims=[REFUS],
        changed_paths=["experiences[1].bullet_sources[2][0]"],
    )
    assert merged["verdict"] == "accepted"
    assert merged["truth_issues"] == []


def test_toute_la_liste_des_citations_changee():
    nouveau = {"claims": [{**REFUS, "status": "supported", "reason": "ok"}]}
    merged = _merge_truth_check(
        nouveau, VALIDATION, RUN, previous_claims=[REFUS], changed_paths=["experiences[1].bullet_sources"],
    )
    assert merged["verdict"] == "accepted"


def test_reference_coupee_jamais_suggeree():
    assert _suggested_refs("La preuve existe ailleurs (pole_s:1…", ["pole_s:14"]) == []
    assert _suggested_refs("La preuve existe ailleurs (pole_s:13).", ["pole_s:14"]) == ["pole_s:13"]


def test_suggestion_lue_sur_la_raison_entiere():
    longue = "x" * 290 + " la preuve est pole_s:13, pas pole_s:14."
    merged = _merge_truth_check(
        {"claims": [{**REFUS, "reason": longue}]}, VALIDATION, RUN,
    )
    (issue,) = merged["truth_issues"]
    assert issue["suggested_refs"] == ["pole_s:13"]
