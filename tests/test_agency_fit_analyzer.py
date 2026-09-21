"""Tests hors ligne du module `agency_analysis` (phase 2 du plan agences).

Aucun réseau : le client IA est un callable injecté qui compte ses appels.
Couverture visée = critères d'acceptation de `aidd_docs/tasks/2026_09/
2026_09_21_targeted_agency_search/phase-2.md` : preuves obligatoires, review
plutôt qu'invention, cache par empreinte, plafond d'appels, persistance qui
survit aux runs, archive Markdown.
"""

from __future__ import annotations

import json

import pytest

from agency_analysis import fit_analyzer
from agency_analysis.fit_analyzer import (
    FitAnalyzer,
    build_payload,
    fingerprint,
    load_cache,
    normalize_analysis,
    public_profile,
    save_cache_atomic,
    store_analysis,
    write_archive_md,
)

AGENCE = {
    "name": "Bew Web Agency",
    "website": "https://www.bew-web-agency.fr/",
    "category": "agence",
    "score": 78,
    "stack": ["WordPress", "Shopify"],
    "address": "401 rue des Pyrénées 75020",
    "distance_m": 2256,
    "snippet": "Agence web Paris, création de sites.",
    "page_texts": [
        {"url": "https://www.bew-web-agency.fr/", "text": "Agence WordPress à Paris, création de sites sur mesure."},
        {"url": "https://www.bew-web-agency.fr/agence", "text": "Équipe de six personnes, WordPress et Shopify."},
    ],
}

PROFIL = {"metiers": ["développeur web", "webmaster"], "localisation": "Paris / IDF"}


def _reponse_ok() -> dict:
    return {
        "strengths": ["Vraie agence WordPress avec équipe identifiée"],
        "weaknesses": ["Orientation SEO marquée, peu de dev sur mesure visible"],
        "application_angle": "Candidater comme webmaster/intégrateur WordPress",
        "fit_summary": "Agence web parisienne WordPress/Shopify, taille humaine.",
        "fit_score": 7,
        "confidence": "haute",
        "category": "agence",
        "evidence_urls": [
            "https://www.bew-web-agency.fr/",
            "https://www.bew-web-agency.fr/agence",
        ],
    }


def _fake_llm(reponses: list[dict] | None = None):
    """Callable injecté : compte les appels, renvoie les réponses fournies.

    Retourne (complete, etat) — `etat["appels"]` compte les appels réels.
    """
    etat = {"appels": 0, "reponses": list(reponses or [])}

    def complete(payload: dict) -> dict:
        etat["appels"] += 1
        if etat["reponses"]:
            return etat["reponses"].pop(0)
        return _reponse_ok()

    return complete, etat


# ── Contrat : empreinte ───────────────────────────────────────────────────────


def test_fingerprint_stable_et_sensible():
    p1 = build_payload(AGENCE, PROFIL)
    p2 = build_payload(AGENCE, PROFIL)
    assert fingerprint(p1) == fingerprint(p2)
    autre = json.loads(json.dumps(p1))
    autre["pages_fournies"][0]["extrait"] += " contenu différent"
    assert fingerprint(p1) != fingerprint(autre)


# ── Contrat : validation de la sortie IA ─────────────────────────────────────


def test_sortie_valide_est_ok_avec_preuves():
    payload = build_payload(AGENCE, PROFIL)
    analyse, problemes = normalize_analysis(_reponse_ok(), AGENCE, payload)
    assert analyse["fit_status"] == "ok"
    assert analyse["fit_score"] == 7
    assert len(analyse["evidence_urls"]) == 2
    assert problemes == []


def test_url_hors_pages_est_rejetee_et_force_review():
    payload = build_payload(AGENCE, PROFIL)
    reponse = _reponse_ok()
    reponse["evidence_urls"] = ["https://site-inconnu.example/preuve-inventee"]
    analyse, problemes = normalize_analysis(reponse, AGENCE, payload)
    assert analyse["evidence_urls"] == []
    assert any("hors des pages fournies" in p for p in problemes)
    assert analyse["fit_status"] == "review"


def test_sortie_non_json_devient_review_sans_invention():
    payload = build_payload(AGENCE, PROFIL)
    analyse, _ = normalize_analysis("pas du json", AGENCE, payload)
    assert analyse["fit_status"] == "review"
    assert analyse["strengths"] == [] and analyse["fit_summary"] == ""


def test_category_le_pipeline_gagne_sur_le_modele():
    payload = build_payload(AGENCE, PROFIL)
    reponse = _reponse_ok()
    reponse["category"] = "formation"  # le modèle se trompe
    analyse, problemes = normalize_analysis(reponse, AGENCE, payload)
    assert analyse["category"] == "agence"
    assert any("pipeline retenu" in p for p in problemes)


def test_fit_score_hors_borne_est_ramene():
    payload = build_payload(AGENCE, PROFIL)
    reponse = _reponse_ok()
    reponse["fit_score"] = 42
    analyse, _ = normalize_analysis(reponse, AGENCE, payload)
    assert analyse["fit_score"] == 10


# ── Cache par domaine + empreinte ────────────────────────────────────────────


def test_cache_hit_ne_rappelle_pas_le_modele(tmp_path):
    complete, etat = _fake_llm()
    analyzer = FitAnalyzer(complete=complete)
    cache = load_cache(tmp_path / "absent.json")

    a1 = analyzer.analyze_agency(AGENCE, PROFIL, cache)
    a2 = analyzer.analyze_agency(AGENCE, PROFIL, cache)

    assert etat["appels"] == 1
    assert a1["cache"] == "miss"
    assert a2["cache"] == "hit"
    assert a2["fit_summary"] == a1["fit_summary"]


def test_fingerprint_change_pousse_l_ancienne_en_histoire(tmp_path):
    cache_path = tmp_path / "cache.json"
    complete, _ = _fake_llm()
    analyzer = FitAnalyzer(complete=complete)
    cache = load_cache(cache_path)
    analyzer.analyze_agency(AGENCE, PROFIL, cache)
    save_cache_atomic(cache_path, cache)

    agence_modifiee = json.loads(json.dumps(AGENCE))
    agence_modifiee["page_texts"][0]["text"] += " Nouvelle offre d'emploi publiée."
    cache2 = load_cache(cache_path)
    complete2, _ = _fake_llm()
    analyzer2 = FitAnalyzer(complete=complete2)
    analyzer2.analyze_agency(agence_modifiee, PROFIL, cache2)
    save_cache_atomic(cache_path, cache2)

    final = load_cache(cache_path)
    entree = final["analyses"]["bew-web-agency.fr"]
    assert entree["fingerprint"] != entree["history"][0]["fingerprint"]
    assert len(entree["history"]) == 1
    # l'ancienne analyse n'est pas détruite, elle est marquée obsolète
    assert entree["history"][0].get("obsolete") is True


def test_agence_absente_du_run_conserve_son_analyse(tmp_path):
    cache_path = tmp_path / "cache.json"
    cache = load_cache(cache_path)
    complete1, _ = _fake_llm()
    FitAnalyzer(complete=complete1).analyze_agency(AGENCE, PROFIL, cache)
    save_cache_atomic(cache_path, cache)

    autre = dict(AGENCE, name="Yateo", website="https://www.yateo.com/")
    cache2 = load_cache(cache_path)
    complete2, _ = _fake_llm()
    FitAnalyzer(complete=complete2).analyze_agency(autre, PROFIL, cache2)
    save_cache_atomic(cache_path, cache2)

    final = load_cache(cache_path)
    assert "bew-web-agency.fr" in final["analyses"]
    assert "yateo.com" in final["analyses"]


def test_cache_corrompu_repart_vide(tmp_path):
    corrompu = tmp_path / "cache.json"
    corrompu.write_text("{pas du json", encoding="utf-8")
    cache = load_cache(corrompu)
    assert cache == fit_analyzer.empty_cache()


# ── Plafond de coût ──────────────────────────────────────────────────────────


def test_lot_plafonne_le_nombre_d_appels(tmp_path, monkeypatch):
    monkeypatch.setattr(fit_analyzer, "DEFAULT_MAX_CALLS", 2)
    complete, etat = _fake_llm()
    analyzer = FitAnalyzer(complete=complete)
    cache = load_cache(tmp_path / "cache.json")
    lot = [
        dict(AGENCE, name=f"Agence {i}", website=f"https://agence{i}.fr/") for i in range(5)
    ]
    stats = analyzer.analyze_batch(lot, PROFIL, cache)
    assert stats["plafond_atteint"] is True
    assert stats["analyzed"] == 2
    assert etat["appels"] == 2
    # les agences au-delà du plafond n'ont pas d'analyse attachée
    assert lot[2].get("analysis") is None


# ── Archive Markdown ─────────────────────────────────────────────────────────


def test_archive_md_ecrite_et_lisible(tmp_path):
    complete, _ = _fake_llm()
    analyzer = FitAnalyzer(complete=complete)
    cache = load_cache(tmp_path / "cache.json")
    lot = [dict(AGENCE)]
    stats = analyzer.analyze_batch(lot, PROFIL, cache)
    archive = write_archive_md(tmp_path / "analyses-test.md", lot, stats, "zone test")
    contenu = archive.read_text(encoding="utf-8")
    assert archive.exists()
    assert "Bew Web Agency" in contenu
    assert "Niveau recherche" in contenu
    assert "Points forts" in contenu


# ── Profil public ────────────────────────────────────────────────────────────


def test_public_profile_lit_criteria_sans_le_master(tmp_path):
    criteria = tmp_path / "criteria.yaml"
    criteria.write_text(
        "user_profile:\n  metiers:\n    - developpeur web\n  ville: Paris\n",
        encoding="utf-8",
    )
    profil = public_profile(criteria)
    assert profil == {"metiers": ["developpeur web"], "ville": "Paris"}


# ── Helpers stdlib : domaine + .env ──────────────────────────────────────────


def test_domain_from_website_normalise():
    from agency_analysis.fit_analyzer import domain_from_website

    assert domain_from_website("https://www.bew-web-agency.fr/") == "bew-web-agency.fr"
    assert domain_from_website("http://YATEO.com/contact") == "yateo.com"
    assert domain_from_website("https://coffee-beans.fr:443/x") == "coffee-beans.fr"
    assert domain_from_website("") == ""
    assert domain_from_website("pas une url") == ""
    assert domain_from_website("https://localhost") == ""


def test_load_env_file_pose_les_absentes_sans_ecraser(tmp_path):
    from agency_analysis.fit_analyzer import load_env_file

    env = tmp_path / ".env"
    env.write_text("TEST_ANALYSE_A=1\n# commentaire\nMAL FORMEE\nTEST_ANALYSE_B= 2 \n", encoding="utf-8")
    import os

    os.environ["TEST_ANALYSE_A"] = "existant"
    try:
        load_env_file(env)
        assert os.environ["TEST_ANALYSE_A"] == "existant"  # setdefault : n'écrase pas
        assert os.environ["TEST_ANALYSE_B"] == "2"
    finally:
        os.environ.pop("TEST_ANALYSE_A", None)
        os.environ.pop("TEST_ANALYSE_B", None)


# ── Client de routage (hors ligne : _call_provider simulé) ───────────────────


def test_parse_json_loose_accepte_les_fences():
    from agency_analysis.fit_analyzer import parse_json_loose

    brut = "```json\n{\"fit_summary\": \"ok\"}\n```"
    assert parse_json_loose(brut) == {"fit_summary": "ok"}
    assert parse_json_loose('{"a": 1}') == {"a": 1}


def test_client_route_tente_le_repli_quand_le_premier_echoue(monkeypatch):
    from agency_analysis.fit_analyzer import RoleRoutingClient

    client = RoleRoutingClient()
    appels = []

    def _faux_call_provider(provider, model, user_message):
        appels.append(provider)
        if provider == "deepseek":
            raise RuntimeError("503")
        return {"fit_summary": "via glm"}

    monkeypatch.setattr(client, "_call_provider", _faux_call_provider)
    data, provider, model = client.complete({"x": 1})
    assert appels == ["deepseek", "glm"]
    assert provider == "glm" and model == "glm-5.3"
    assert data == {"fit_summary": "via glm"}


def test_client_route_echoue_proprement_si_tout_tombe(monkeypatch):
    import pytest

    from agency_analysis.fit_analyzer import RoleRoutingClient

    client = RoleRoutingClient()

    def _faux_call_provider(provider, model, user_message):
        raise RuntimeError(f"{provider} down")

    monkeypatch.setattr(client, "_call_provider", _faux_call_provider)
    with pytest.raises(RuntimeError, match="tous les fournisseurs"):
        client.complete({"x": 1})
