"""Chaîne CV pilotée par des agents IA : point d'entrée.

Le code est réparti en modules, ce fichier garde l'orchestration
(``AICVPipeline``) et réexporte tout le reste : ``from cv_generator.ai_agents
import X`` continue de fonctionner pour chaque nom existant.

- ai_client   : fournisseurs d'IA, routage par rôle, lecture du JSON ;
- ai_prompts  : prompts des cinq rôles ;
- ai_plan     : contexte envoyé aux agents, validation du plan de l'analyste ;
- ai_assembly : assemblage du CV, fusion des verdicts, contrat de correction ;
- ai_patch    : mode patch du réviseur.
"""

from __future__ import annotations

from typing import Any, Dict, List

from cv_generator.cv_creator import build_structural_shell
from cv_generator.cv_quality_checker import review_cv as review_cv_rules
from cv_generator.cv_truth_validator import validate_cv_content
from cv_generator.job_analyzer import analyze_job_for_cv as analyze_job_rules
from cv_generator import rules as candidate_rules
from .ai_client import (  # noqa: F401  (réexport)
    AgentClient,
    AgentResult,
    BUDGET_HINT,
    CVAgentError,
    CVLLMClient,
    _check_completion,
    _parse_json_response,
)
from .ai_prompts import (  # noqa: F401  (réexport)
    ANALYZER_PROMPT,
    CREATOR_PROMPT,
    REVIEWER_PROMPT,
    REVISER_PROMPT,
    TRUTH_CHECKER_PROMPT,
    _PATCH_MODE_PROMPT,
    _standing_preference_clause,
)
from .ai_plan import (  # noqa: F401  (réexport)
    without_contact,
    _agent_call,
    _agent_run,
    _allowed_skills,
    _announcement_context,
    _as_string_list,
    _candidate_instructions,
    _candidate_title,
    _clip,
    _filter_skills_whitelist,
    _int_score,
    _required_experiences,
    _sanitize_skill_mapping,
    _truth_context,
    _validate_announcement,
    _validate_plan,
    _validate_presentation_strategy,
    visible_experience_catalog,
)
from .ai_assembly import (  # noqa: F401  (réexport)
    SOURCE_GAP_CODE,
    _PYTHON_OWNED_PATHS,
    _assemble_cv_content,
    _claim_affected,
    _cv_diff_paths,
    _filter_education_by_variant,
    _is_python_owned,
    _is_source_gap,
    _merge_review,
    _merge_truth_check,
    _normalize_evidence_coverage,
    _normalize_problems,
    _path_segments,
    build_correction_contract,
    correction_fingerprint,
    to_writer_schema,
)
from .ai_patch import (  # noqa: F401  (réexport)
    _apply_cv_patch,
    _parse_patch_path,
    _patch_parent,
    _patch_path_in_scope,
    _patch_scope,
    _patch_token_matches,
    _wrap_patched_cv,
)


class AICVPipeline:
    def __init__(self, client: AgentClient | None = None) -> None:
        self.client = client or CVLLMClient()
        #: Échecs de patch consécutifs du réviseur : à 2, on cesse de lui
        #: proposer le mode patch et on repasse en réécriture complète.
        self._patch_failures = 0

    def analyze(self, job: Dict[str, Any], master: Dict[str, Any]) -> Dict[str, Any]:
        rule_plan = analyze_job_rules(job, master)
        result = _agent_call(
            self.client,
            "cv_job_analyzer",
            ANALYZER_PROMPT,
            {
                "annonce_complete": _announcement_context(job),
                "consignes_candidat": _candidate_instructions(job),
                "familles_de_poste": list(candidate_rules.JOB_FAMILIES),
                "source_verite": _truth_context(master, "analyzer"),
                "preanalyse_python": rule_plan,
            },
        )
        return _validate_plan(result.data, rule_plan, master, result)

    def create(
        self,
        job: Dict[str, Any],
        master: Dict[str, Any],
        plan: Dict[str, Any],
    ) -> Dict[str, Any]:
        result = _agent_call(
            self.client,
            "cv_creator",
            CREATOR_PROMPT + _standing_preference_clause(master, plan, "creator"),
            {
                "annonce_complete": _announcement_context(job),
                "consignes_candidat": _candidate_instructions(job),
                "source_verite": _truth_context(master, "creator"),
                "plan_adaptation": plan,
                # Le squelette ne porte que ce qui n'est pas éditorial :
                # localisation, langues et contraintes de gabarit. Les
                # coordonnées restent côté Python.
                "squelette_structurel": without_contact(build_structural_shell(
                    master, str(plan.get("selected_base_variant") or "")
                )),
            },
        )
        return _assemble_cv_content(
            result.data,
            job,
            master,
            plan,
            result,
            "cv_creator_ai",
        )

    def verify(
        self,
        job: Dict[str, Any],
        master: Dict[str, Any],
        plan: Dict[str, Any],
        draft: Dict[str, Any],
        previous_content: Dict[str, Any] | None = None,
        previous_truth: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Contrôle la vérité avant tout jugement éditorial.

        Python passe en premier : une référence introuvable n'a pas besoin d'un
        appel IA pour être refusée. L'agent n'est consulté que sur ce que Python
        ne peut pas voir — l'écart de sens entre une preuve et sa reformulation.

        Après une révision, le contrôle devient ciblé : Python diff le contenu
        validé et le contenu révisé, l'agent ne re-juge que les chemins
        modifiés, les chemins intacts gardent leur verdict précédent. Si rien
        n'a bougé, aucun appel IA n'est dépensé du tout.
        """
        validation = validate_cv_content(draft, master, plan)
        previous_claims: List[Dict[str, Any]] | None = None
        changed_paths: List[str] = []
        if previous_content is not None and previous_truth is not None:
            changed_paths = _cv_diff_paths(
                previous_content.get("cv", {}), draft.get("cv", {})
            )
            previous_claims = [
                item for item in previous_truth.get("claims") or [] if isinstance(item, dict)
            ]
            if not changed_paths:
                # Rien n'a bougé : le verdict précédent reste exact. Python
                # re-valide tout le CV (gratuit), l'agent n'est pas rappelé.
                previous_run = previous_truth.get("agent_run") or {}
                inherited = AgentResult(
                    data={},
                    provider=str(previous_run.get("provider") or "injected"),
                    model=str(previous_run.get("model") or "injected"),
                    duration_seconds=0.0,
                )
                merged = _merge_truth_check(
                    {"claims": previous_claims},
                    validation,
                    inherited,
                    previous_claims=previous_claims,
                    changed_paths=[],
                )
                merged["agent_run"]["reused"] = True
                return merged

        payload = {
            "source_verite": _truth_context(master, "reviewer"),
            "cv_a_verifier": without_contact(draft.get("cv", {})),
            "controle_python": validation["issues"],
        }
        if previous_claims is not None and changed_paths:
            payload["verification_ciblee"] = {
                "consigne": (
                    "Seuls les chemins listés dans chemins_modifies ont changé depuis la "
                    "validation précédente : concentre l'analyse de sens sur eux, en rendant "
                    "un claim par chemin modifié. Les chemins intacts listés dans "
                    "statuts_deja_valides portent exactement le même texte qu'au tour "
                    "précédent où ils ont été jugés : ne les re-analyse pas, leur statut "
                    "antérieur sera conservé tel quel."
                ),
                "chemins_modifies": changed_paths[:60],
                "statuts_deja_valides": [
                    {"path": item.get("path"), "status": item.get("status")}
                    for item in previous_claims
                    if not _claim_affected(str(item.get("path") or ""), changed_paths)
                ][:80],
            }
        result = _agent_call(
            self.client,
            "cv_truth_checker",
            TRUTH_CHECKER_PROMPT,
            payload,
        )
        return _merge_truth_check(
            result.data,
            validation,
            result,
            previous_claims=previous_claims,
            changed_paths=changed_paths or None,
        )

    def review(
        self,
        job: Dict[str, Any],
        master: Dict[str, Any],
        plan: Dict[str, Any],
        draft: Dict[str, Any],
    ) -> Dict[str, Any]:
        deterministic = review_cv_rules(job, master, plan, draft)
        result = _agent_call(
            self.client,
            "cv_quality_checker",
            REVIEWER_PROMPT + _standing_preference_clause(master, plan, "reviewer"),
            {
                "annonce_complete": _announcement_context(job),
                "consignes_candidat": _candidate_instructions(job),
                "source_verite": _truth_context(master, "reviewer"),
                "plan_adaptation": plan,
                "cv_a_juger": without_contact(draft),
                "controle_python": deterministic,
            },
        )
        return _merge_review(result.data, deterministic, result, master)

    def revise(
        self,
        job: Dict[str, Any],
        master: Dict[str, Any],
        plan: Dict[str, Any],
        draft: Dict[str, Any],
        review: Dict[str, Any],
        truth_check: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        contract = build_correction_contract(review, truth_check)
        payload = {
            "annonce_complete": _announcement_context(job),
            "consignes_candidat": _candidate_instructions(job),
            "source_verite": _truth_context(master, "reviser"),
            "plan_adaptation": plan,
            "brouillon": to_writer_schema(draft),
            "jugement": review,
            "corrections_a_appliquer": contract,
        }

        # Mode patch : le réviseur ne rend que les chemins à corriger, Python
        # applique mécaniquement — le reste du CV reste identique au brouillon,
        # aucune partie validée ne peut régresser. Après deux échecs de patch
        # consécutifs, repli durable sur la réécriture complète.
        final = None
        if getattr(self, "_patch_failures", 0) < 2:
            scope = _patch_scope(contract)
            if scope:
                result = _agent_call(
                    self.client,
                    "cv_style_reviser",
                    REVISER_PROMPT + "\n\n" + _PATCH_MODE_PROMPT,
                    payload,
                )
                data = result.data
                if isinstance(data, dict) and isinstance(data.get("changes"), list):
                    try:
                        flat = _apply_cv_patch(payload["brouillon"], data["changes"], scope)
                    except CVAgentError as patch_error:
                        # Le patch est refusé : l'erreur localisée part avec le
                        # contrat de l'appel de repli, sans quoi le réviseur
                        # réécrirait à l'aveugle la cause de son propre échec.
                        self._patch_failures = getattr(self, "_patch_failures", 0) + 1
                        contract = contract + [
                            {
                                "origin": "patch",
                                "blocking": True,
                                "code": "PATCH_REFUSE",
                                "location": None,
                                "problem": str(patch_error),
                                "suggested_fix": (
                                    "Renvoie cette fois le schéma complet du rédacteur."
                                ),
                            }
                        ]
                        payload["corrections_a_appliquer"] = contract
                    else:
                        self._patch_failures = 0
                        final = _wrap_patched_cv(
                            draft, flat, job, master, plan, result
                        )
                elif isinstance(data, dict) and data.get("experiences"):
                    # Le modèle a rendu le schéma complet malgré la consigne
                    # patch : chemin historique, toléré sans compter un échec.
                    final = _assemble_cv_content(
                        data,
                        job,
                        master,
                        plan,
                        result,
                        "cv_style_reviser_ai",
                    )
                else:
                    # Ni patch ni schéma complet : échec de patch, le repli
                    # ci-dessous referme le tour.
                    self._patch_failures = getattr(self, "_patch_failures", 0) + 1
                    contract = contract + [
                        {
                            "origin": "patch",
                            "blocking": True,
                            "code": "PATCH_ILLISIBLE",
                            "location": None,
                            "problem": (
                                "La réponse précédente n'était ni un patch « changes » "
                                "ni le schéma complet du rédacteur."
                            ),
                            "suggested_fix": "Renvoie le schéma complet du rédacteur.",
                        }
                    ]
                    payload["corrections_a_appliquer"] = contract

        if final is None:
            result = _agent_call(
                self.client,
                "cv_style_reviser",
                REVISER_PROMPT,
                payload,
            )
            final = _assemble_cv_content(
                result.data,
                job,
                master,
                plan,
                result,
                "cv_style_reviser_ai",
            )
        # Dernier passage obligatoire : quelle que soit la voie (patch ciblé ou
        # réécriture complète), la section compétences repasse par la liste
        # blanche du profil maître avant de sortir de la révision.
        final["skills"] = _filter_skills_whitelist(final.get("skills"), master)
        final["source_draft_agent"] = draft.get("agent")
        final["review_applied"] = {
            "initial_quality_score": review.get("quality_score"),
            "initial_ats_score": review.get("ats_score"),
            "status_before_revision": review.get("status"),
            "problem_count": len(review.get("problems", [])),
            "truth_verdict_before_revision": (truth_check or {}).get("verdict"),
        }
        return final
