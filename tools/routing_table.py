"""Tableau du routage IA par rôle, généré depuis config/ai_role_routing.json.

``python -m tools.routing_table`` affiche le tableau Markdown recopié dans
docs/CV_CLI_BRIDGE.md ; tests/test_ai_role_routing.py vérifie qu'ils
concordent, pour que la doc ne promette plus un modèle que la config n'utilise pas.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ROLE_LABELS = {
    "job_offer_analyzer": "Filtrage des annonces",
    "cv_job_analyzer": "Analyse de l'annonce (plan du CV, famille de poste)",
    "cv_creator": "Rédaction du CV",
    "cv_truth_checker": "Vérification de véracité",
    "cv_quality_checker": "Juge qualité",
    "cv_style_reviser": "Correction (révision)",
    "agent_redacteur_lettres": "Lettre de motivation",
    "company_verifier": "Vérification d'entreprise",
    "agency_fit": "Adéquation d'agence",
}


def _step_label(model: dict) -> str:
    label = f"{model.get('provider')} `{model.get('model', '')}`"
    if model.get("reasoning_effort"):
        label += f" ({model['reasoning_effort']})"
    return label


def routing_table(config_path: Path = ROOT / "config" / "ai_role_routing.json") -> str:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    models = config["models"]
    rows = ["| Rôle | Ordre d'essai (principal, puis secours) |", "|---|---|"]
    for role, steps in config["roles"].items():
        chain = " → ".join(_step_label(models[step]) for step in steps)
        rows.append(f"| {ROLE_LABELS.get(role, role)} (`{role}`) | {chain} |")
    return "\n".join(rows)


if __name__ == "__main__":
    print(routing_table())
