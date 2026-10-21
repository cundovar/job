"""
Variante de CV recommandée pour une offre.

Deux sources, dans cet ordre :
1. le plan de l'agent analyste (``recommendation_from_plan``), qui a lu
   l'annonce complète : c'est lui que suivent le CV et la lettre ;
2. à défaut (offre en cache jamais analysée, analyse en échec), la sélection
   par mots-clés de ``cv_generator.job_analyzer.select_variant``, la même que
   celle de la préanalyse du CV.

Il n'existe plus de second algorithme de score ici : le CV et la lettre
partaient sur deux variantes différentes quand chacun avait le sien.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List

from cv_generator.job_analyzer import select_variant

DEFAULT_MASTER_PATH = "data/cv_master_profile.json"


@dataclass(frozen=True)
class CVRecommendation:
    cv_id: str
    cv_name: str
    score: int
    matched_keywords: List[str]
    reason: str


def load_master_profile(path: str | None = None) -> Dict[str, Any]:
    with open(path or os.getenv("CV_MASTER_PROFILE", DEFAULT_MASTER_PATH), "r", encoding="utf-8") as f:
        return json.load(f) or {}


def _variant_name(master: Dict[str, Any], variant: Dict[str, Any]) -> str:
    variant_id = str(variant.get("id") or "")
    titles = master.get("positioning", {}).get("title_variants", {})
    return titles.get(variant_id) or variant.get("title") or variant_id


def recommend_cv(job: Dict[str, Any], master: Dict[str, Any] | None = None) -> CVRecommendation:
    master = master if master is not None else load_master_profile()
    if not master.get("cv_variants"):
        raise ValueError("Aucune variante de CV dans cv_master_profile.json")
    variant, score, matched = select_variant(job, master)
    if matched:
        reason = "Correspondance avec: " + ", ".join(matched[:5])
    else:
        reason = "Aucun mot-cle fort detecte; variante par defaut selon positioning.default_priority."
    return CVRecommendation(
        cv_id=str(variant.get("id") or ""),
        cv_name=_variant_name(master, variant),
        score=score,
        matched_keywords=matched,
        reason=reason,
    )


def recommendation_from_plan(plan: Dict[str, Any], master: Dict[str, Any]) -> CVRecommendation:
    """La variante retenue par l'agent analyste, présentée comme une recommandation."""
    variant_id = str(plan.get("selected_base_variant") or "")
    variant = next(
        (item for item in master.get("cv_variants", []) if item.get("id") == variant_id),
        {"id": variant_id},
    )
    family = (plan.get("annonce") or {}).get("famille") or ""
    return CVRecommendation(
        cv_id=variant_id,
        cv_name=_variant_name(master, variant),
        score=0,
        matched_keywords=list(plan.get("priority_keywords") or [])[:5],
        reason="Variante choisie par l'analyse IA de l'annonce"
        + (f" (famille de poste : {family})" if family else "")
        + ".",
    )
