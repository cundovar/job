"""Mode patch du réviseur : application mécanique des seuls chemins à corriger.

Extrait de cv_generator/ai_agents.py, sans changement de comportement.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List

from .ai_assembly import _assemble_cv_content
from .ai_client import AgentResult, CVAgentError


def _parse_patch_path(path: Any) -> List[Any]:
    """« experiences[1].bullets[2] » → [("experiences", 1), ("bullets", 2)]."""
    tokens: List[Any] = []
    for part in str(path or "").split("."):
        match = re.fullmatch(r"([a-z_]+)(?:\[(\d+)\])?", part.strip())
        if not match:
            raise CVAgentError(f"Chemin de patch invalide : « {path} ».")
        name, index = match.group(1), match.group(2)
        tokens.append((name, int(index) if index is not None else None))
    if not tokens:
        raise CVAgentError("Chemin de patch vide.")
    return tokens


def _patch_scope(contract: List[Dict[str, Any]]) -> List[List[Any]]:
    """Les préfixes de chemins que le patch a le droit de toucher.

    Seules les erreurs bloquantes — vérité et gabarit — définissent le
    périmètre : un patch n'existe pas pour aller retoucher du cosmétique.
    La valeur « cv » (affirmation interdite sans localisation fine) ouvre tout.
    """
    prefixes: List[List[Any]] = []
    for item in contract or []:
        if item.get("origin") not in {"truth", "format"}:
            continue
        location = item.get("location")
        if not location:
            continue
        try:
            prefixes.append(_parse_patch_path(location))
        except CVAgentError:
            continue
    return prefixes


def _patch_token_matches(prefix_token: Any, path_token: Any) -> bool:
    """Un segment de contrat couvre-t-il un segment de chemin ?

    Un contrat sans index — « experiences » pour `TOO_MANY_EXPERIENCES`,
    « skills » pour `TOO_MANY_SKILL_SECTIONS` — porte sur la liste entière :
    il ouvre donc chacun de ses éléments, sans quoi la seule correction
    possible (retirer l'élément de trop) serait refusée comme hors périmètre.
    """
    name, index = prefix_token
    other_name, other_index = path_token
    if name != other_name:
        return False
    return index is None or index == other_index


def _patch_path_in_scope(tokens: List[Any], prefixes: List[List[Any]]) -> bool:
    for prefix in prefixes:
        if prefix and prefix[0] == ("cv", None):
            return True
        if len(tokens) < len(prefix):
            continue
        if all(
            _patch_token_matches(prefix_token, path_token)
            for prefix_token, path_token in zip(prefix, tokens)
        ):
            return True
    return False


def _patch_parent(flat: Dict[str, Any], tokens: List[Any]) -> Any:
    """Navigue vers le parent du dernier token ; renvoie (conteneur, clé)."""
    node: Any = flat
    for name, index in tokens[:-1]:
        if index is None:
            if not isinstance(node, dict) or name not in node:
                raise CVAgentError(f"Chemin de patch introuvable : « {name} ».")
            node = node[name]
        else:
            if not isinstance(node, dict) or name not in node:
                raise CVAgentError(f"Chemin de patch introuvable : « {name} ».")
            container = node[name]
            if not isinstance(container, list) or index >= len(container):
                raise CVAgentError(f"Index de patch hors limites : « {name}[{index}] ».")
            node = container[index]
    name, index = tokens[-1]
    if index is None:
        if not isinstance(node, dict):
            raise CVAgentError(f"Chemin de patch invalide pour la cible « {name} ».")
        return node, name
    if not isinstance(node, dict) or name not in node:
        raise CVAgentError(f"Chemin de patch introuvable : « {name} ».")
    container = node[name]
    if not isinstance(container, list) or index >= len(container):
        raise CVAgentError(f"Index de patch hors limites : « {name}[{index}] ».")
    return container, index


def _apply_cv_patch(
    flat: Dict[str, Any],
    changes: Any,
    scope: List[List[Any]],
) -> Dict[str, Any]:
    """Applique les changements du réviseur aux seuls chemins ciblés.

    Python est un exécuteur mécanique : il pose la valeur rendue par l'agent
    à l'endroit demandé et ne touche à rien d'autre — le reste du CV reste
    identique octet pour octet au brouillon entrant.
    """
    if not isinstance(changes, list) or not changes:
        raise CVAgentError("Patch vide : la liste « changes » est absente ou vide.")

    # Lecture complète avant la moindre écriture : un patch dont un seul
    # changement est illisible ou hors périmètre est refusé en bloc, jamais
    # appliqué à moitié.
    lus: List[Any] = []
    for change in changes:
        if not isinstance(change, dict):
            raise CVAgentError("Changement de patch illisible (élément non objet).")
        action = str(change.get("action") or "").strip().lower()
        if action not in {"modify", "remove"}:
            raise CVAgentError(
                f"Action de patch inconnue : « {change.get('action')} »."
            )
        tokens = _parse_patch_path(change.get("path"))
        if not _patch_path_in_scope(tokens, scope):
            raise CVAgentError(
                f"Chemin de patch hors périmètre du contrat : « {change.get('path')} »."
            )
        lus.append((action, tokens, change))

    # Les index d'un patch désignent tous le brouillon *entrant*. Une
    # suppression appliquée trop tôt décale la liste, et la correction
    # suivante atterrit sur la puce voisine — texte de l'agent posé sur la
    # mauvaise preuve, sans que le validateur puisse le voir. On modifie
    # donc d'abord, à index stables, puis on supprime du dernier au premier.
    modifications = [item for item in lus if item[0] == "modify"]
    suppressions = sorted(
        (item for item in lus if item[0] == "remove"),
        key=lambda item: tuple(
            (name, -1 if index is None else index) for name, index in item[1]
        ),
        reverse=True,
    )

    updated = copy.deepcopy(flat)
    for _, tokens, change in modifications:
        container, key = _patch_parent(updated, tokens)
        new = change.get("new")
        container[key] = new
        # Une puce réécrite doit rester sourcée : on refuse tout de suite ce
        # que le validateur bloquerait plus tard, avec la localisation.
        if tokens[-1][0] == "bullets" and tokens[-1][1] is not None:
            if not isinstance(new, dict) or not str(new.get("text") or "").strip():
                raise CVAgentError(
                    f"Puce modifiée sans texte : « {change.get('path')} »."
                )
            if not isinstance(new.get("sources"), list) or not new["sources"]:
                raise CVAgentError(
                    f"Puce modifiée sans preuve citée : « {change.get('path')} »."
                )

    for _, tokens, change in suppressions:
        container, key = _patch_parent(updated, tokens)
        if not isinstance(container, list):
            raise CVAgentError(
                f"« remove » ne s'applique pas à « {change.get('path')} »."
            )
        del container[key]

    return updated


def _wrap_patched_cv(
    draft: Dict[str, Any],
    flat: Dict[str, Any],
    job: Dict[str, Any],
    master: Dict[str, Any],
    plan: Dict[str, Any],
    result: AgentResult,
) -> Dict[str, Any]:
    """Réassemble le CV autour du contenu patché.

    Le flat patché est au schéma rédacteur (puces {text, sources}) : on le
    repasse dans l'assemblage déterministe — mêmes identifiants, donc mêmes
    intitulés et mêmes preuves pour tout ce que le patch n'a pas touché. La
    sortie reste byte-identique au brouillon hors chemins ciblés.
    """
    final = _assemble_cv_content(
        flat,
        job,
        master,
        plan,
        result,
        "cv_style_reviser_ai",
    )
    final["source_draft_agent"] = draft.get("agent")
    return final
