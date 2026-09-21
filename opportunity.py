"""La convergence : transformer des constats vérifiés en objet consommable par cv_generator.

POINT CRITIQUE. `cv_generator.utils.job_text()` aplatit `title`, `company`,
`description`, `requirements`, `sector`, `contract_type` et `location` en un
simple bloc de texte. Tout ce qu'on y met devient la vérité de référence pour la
sélection de la variante de CV, et le contrôle de véracité existant ne l'attrapera
pas : `cv_assessment` vérifie ce qu'on affirme sur le **candidat**, pas sur
l'entreprise.

Conséquence appliquée ici : seuls les constats `CONFIRMED` entrent dans
`description`. Aucun `UNCERTAIN`, aucune hypothèse. Sans constat confirmé,
`build_opportunity` retourne `None` et le pipeline passe à l'entreprise suivante.
Il n'existe pas de repli sur une candidature générique.
"""
from __future__ import annotations

from typing import Any, Dict, List

from company_analysis.verifier import (
    CONFIRMED,
    DESCRIPTION_CATEGORIES,
    confirmed_only,
)

MISSION = "spontaneous"
SOURCE = "prospection_spontanee"


def _description(company_name: str, findings: List[Dict[str, Any]]) -> str:
    """Compose la description à partir des seuls constats confirmés."""
    lines = [
        f"Candidature spontanée auprès de {company_name}.",
        "",
        "Ce qui est établi sur cette structure, chaque point étant adossé à une mesure :",
        "",
    ]
    for finding in findings:
        lines.append(f"- {finding['claim']}")
    lines.extend(
        [
            "",
            "Aucun autre élément n'a pu être vérifié. Ce qui n'apparaît pas ci-dessus "
            "n'est pas connu et ne doit pas être supposé.",
        ]
    )
    return "\n".join(lines)


def build_opportunity(
    company: Dict[str, Any],
    claims: List[Dict[str, Any]],
    target_title: str,
) -> Dict[str, Any] | None:
    """Produit l'objet attendu par cv_generator, ou None s'il n'y a rien de prouvé."""
    confirmed = confirmed_only(claims)
    if not confirmed:
        return None

    describable = [
        claim for claim in confirmed if claim.get("category") in DESCRIPTION_CATEGORIES
    ]
    if not describable:
        # Un contact public vérifié ne dit rien de l'entreprise : ça ne suffit
        # pas à motiver une candidature.
        return None

    company_name = str(company.get("nom") or "").strip()
    if not target_title:
        raise ValueError(
            f"Aucun poste visé déclaré pour {company_name or 'cette structure'}. "
            "L'intitulé vient de config/companies.yaml, il n'est jamais déduit du site."
        )

    contacts = [
        claim for claim in confirmed if claim.get("category") == "contact"
    ]

    return {
        # Clés communes avec les scrapers : cv_generator ne fait pas la différence.
        "title": target_title,
        "company": company_name,
        "location": str(company.get("ville") or "").strip(),
        # L'adresse vient du CSV, relevée à la main. Elle est recopiée telle quelle :
        # une ville seule ne devient jamais une adresse, et un code postal n'est
        # jamais déduit d'une adresse absente.
        "address": str(company.get("adresse") or "").strip(),
        "postal_code": str(company.get("code_postal") or "").strip(),
        "description": _description(company_name, describable),
        "url": str(company.get("site") or "").strip(),
        "source": SOURCE,
        # Spécifique à la voie spontanée.
        "mission": MISSION,
        "findings": [
            {
                "claim": claim["claim"],
                "evidence": claim["evidence"],
                "status": CONFIRMED,
                "source_tool": claim["source_tool"],
                "category": claim["category"],
            }
            for claim in confirmed
        ],
        "public_contact": [
            {"claim": claim["claim"], "evidence": claim["evidence"]} for claim in contacts
        ],
        "company_type": str(company.get("type") or "").strip(),
        "company_status": str(company.get("statut") or "").strip(),
    }
