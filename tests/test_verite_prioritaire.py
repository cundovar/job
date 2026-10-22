"""La vérité l'emporte sur la pertinence (Mairie de Dugny, 22/10/2026).

Le juge redemandait l'intitulé exact de l'annonce (« … d'accueil social ») que
le vérificateur venait de refuser : trois tours d'aller-retour, CV bloqué.
"""
from cv_generator.ai_agents import AgentResult, AICVPipeline, _truth_first


def test_une_remarque_du_juge_sur_un_chemin_refuse_par_la_verite_tombe():
    contract = [
        {"origin": "relevance", "path": "title", "location": "title", "code": "ATS_TITLE", "problem": "Reprendre l'intitulé."},
        {"origin": "relevance", "path": "skills[0]", "location": "skills[0]", "code": "X", "problem": "Autre."},
        {"origin": "truth", "location": "title", "code": "CLAIM_NOT_SUPPORTED_BY_SOURCE", "problem": "« social » non prouvé."},
    ]
    out = _truth_first(contract, {"title": ["Agent polyvalent d'accueil social"]})
    assert [(item["origin"], item["code"]) for item in out] == [
        ("relevance", "X"), ("truth", "CLAIM_NOT_SUPPORTED_BY_SOURCE")]
    assert out[1]["formulations_refusees"] == ["Agent polyvalent d'accueil social"]


class _Client:
    def __init__(self):
        self.review_payloads = []

    def complete_json(self, *, agent_name, system_prompt, payload):
        if agent_name == "cv_truth_checker":
            return AgentResult({"claims": [{"path": "title", "status": "unsupported", "reason": "« social » non prouvé."}]}, "t", "t")
        self.review_payloads.append(payload)
        return AgentResult({"status": "validated", "problems": []}, "t", "t")


def test_le_juge_voit_les_formulations_deja_refusees():
    client = _Client()
    agents = AICVPipeline(client)
    draft = {"cv": {"title": "Agent polyvalent d'accueil social", "profile": "P.", "experiences": []}}
    agents.verify({}, {}, {}, draft)
    agents.review({"title": "Poste"}, {}, {}, draft)
    assert {"path": "title", "formulations_refusees": ["Agent polyvalent d'accueil social"]} in (
        client.review_payloads[0]["refus_verite"])
