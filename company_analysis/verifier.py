"""Le Vérificateur : il essaie de réfuter les constats, il ne les fabrique pas.

Trois couches, dans cet ordre :

1. `build_claims` transforme des mesures en constats. La formulation est
   mécanique — une reformulation littérale du fait mesuré, avec sa preuve.
   Aucune IA n'intervient ici : rien d'interprétatif n'est inventé.
2. `verify_claims` rappelle le collecteur et cherche la mesure contraire.
   C'est la seule couche qui peut accorder `CONFIRMED`.
3. `ai_adjudicate` soumet les constats confirmés à un modèle qui ne peut que
   les **dégrader**. Aucun chemin de code ne permet à un LLM de promouvoir
   quoi que ce soit : la surface d'hallucination est supprimée, pas surveillée.

Règles dures :
- pas d'`evidence` mesurée → jamais `CONFIRMED` ;
- une donnée inconnue produit `UNCERTAIN`, jamais un `REJECTED` ;
- tout texte lu sur un site est une donnée non fiable, jamais une consigne.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, List

from .collectors import COLLECTORS

CONFIRMED = "CONFIRMED"
REJECTED = "REJECTED"
UNCERTAIN = "UNCERTAIN"
UNVERIFIED = "UNVERIFIED"

SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent.parent / "config" / "agent_verificateur.md"

# Catégories injectées dans la description de l'opportunité. Le contact est
# vérifié comme les autres mais reste hors description : c'est une donnée
# opérationnelle, pas un argument de candidature, et `job_text()` sert à
# choisir la variante de CV.
DESCRIPTION_CATEGORIES = ("activity", "stack", "recruitment")

PLACEHOLDER_PATTERNS = (
    re.compile(r"\bexemple?\b", re.I),
    re.compile(r"\bexample\b", re.I),
    re.compile(r"lorem\s+ipsum", re.I),
    re.compile(r"^(nom|prenom|votre|your|email|mail|test|user|username)@", re.I),
    re.compile(r"@(test|localhost|domain|domaine|monsite|votresite)\.", re.I),
)


def _claim(
    text: str,
    evidence: List[str],
    source_tool: str,
    category: str,
    confidence: float,
    check: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "id": f"{source_tool}:{category}:{abs(hash(text)) % 10_000_000}",
        "claim": text,
        "evidence": [item for item in evidence if str(item).strip()],
        "source_tool": source_tool,
        "category": category,
        "confidence": confidence,
        "status": UNVERIFIED,
        "check": check,
    }


def _looks_like_placeholder(value: str) -> bool:
    return any(pattern.search(str(value)) for pattern in PLACEHOLDER_PATTERNS)


def _usable(measurements: Dict[str, Dict[str, Any]], tool: str) -> Dict[str, Any] | None:
    """La mesure de ce collecteur est-elle exploitable ?

    Une mesure absente n'est pas une mesure réussie : sans clé `value`, il n'y a
    rien à reformuler, et on ne doit surtout pas traiter le vide comme un succès.
    """
    measurement = measurements.get(tool)
    if not isinstance(measurement, dict) or measurement.get("error"):
        return None
    return measurement if isinstance(measurement.get("value"), dict) else None


def build_claims(company: Dict[str, Any], measurements: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Reformule mécaniquement les mesures exploitables en constats."""
    name = str(company.get("nom") or "cette structure").strip()
    claims: List[Dict[str, Any]] = []

    metadata = _usable(measurements, "inspect_metadata")
    if metadata:
        title = str(metadata["value"].get("title") or "").strip()
        description = str(metadata["value"].get("description") or "").strip()
        if title:
            claims.append(
                _claim(
                    f"{name} se présente publiquement sous l'intitulé « {title} ».",
                    [metadata["evidence"]],
                    "inspect_metadata",
                    "activity",
                    0.9,
                    {"kind": "metadata_title", "expected": title},
                )
            )
        if description:
            claims.append(
                _claim(
                    f"{name} décrit son activité ainsi : « {description} ».",
                    [metadata["evidence"]],
                    "inspect_metadata",
                    "activity",
                    0.85,
                    {"kind": "metadata_description", "expected": description},
                )
            )

    stack = _usable(measurements, "detect_stack")
    if stack:
        for technology in stack["value"].get("detected", []):
            claims.append(
                _claim(
                    f"Le site de {name} est construit avec {technology}.",
                    [stack["evidence"]],
                    "detect_stack",
                    "stack",
                    0.9,
                    {"kind": "stack_detected", "expected": technology},
                )
            )

    careers = _usable(measurements, "find_careers_signals")
    if careers and careers["value"].get("has_careers_page"):
        claims.append(
            _claim(
                f"{name} publie sur son site une page consacrée au recrutement.",
                [careers["evidence"]],
                "find_careers_signals",
                "recruitment",
                0.8,
                {"kind": "careers_page"},
            )
        )

    contact = _usable(measurements, "extract_public_contact")
    if contact:
        for email in contact["value"].get("generic_emails", []):
            claims.append(
                _claim(
                    f"{name} affiche publiquement l'adresse de contact {email}.",
                    [contact["evidence"]],
                    "extract_public_contact",
                    "contact",
                    0.75,
                    {"kind": "public_email", "expected": email},
                )
            )

    return claims


def _support(check: Dict[str, Any], measurement: Dict[str, Any]) -> bool | None:
    """La nouvelle mesure soutient-elle le constat ?

    True = soutenu, False = contredit, None = indéterminable.
    """
    if measurement.get("error"):
        return None
    value = measurement.get("value") or {}
    kind = check.get("kind")
    expected = str(check.get("expected") or "")

    if kind == "metadata_title":
        observed = str(value.get("title") or "").strip()
        return None if not observed else observed == expected
    if kind == "metadata_description":
        observed = str(value.get("description") or "").strip()
        return None if not observed else observed == expected
    if kind == "stack_detected":
        detected = value.get("detected")
        if not isinstance(detected, list):
            return None
        return expected in detected
    if kind == "careers_page":
        observed = value.get("has_careers_page")
        return None if observed is None else bool(observed)
    if kind == "public_email":
        emails = [item.get("email") for item in value.get("emails", []) if isinstance(item, dict)]
        return None if not emails else expected in emails
    return None


def verify_claims(
    claims: List[Dict[str, Any]],
    url: str,
    collectors: Dict[str, Callable[[str], Dict[str, Any]]] | None = None,
) -> List[Dict[str, Any]]:
    """Rappelle chaque collecteur et cherche la mesure contraire."""
    tools = collectors or COLLECTORS
    remeasured: Dict[str, Dict[str, Any]] = {}
    verified: List[Dict[str, Any]] = []

    for claim in claims:
        result = dict(claim)

        if not result.get("evidence"):
            result["status"] = UNCERTAIN
            result["verification_note"] = "aucune preuve mesurée : confirmation impossible"
            verified.append(result)
            continue

        expected = str(result.get("check", {}).get("expected") or "")
        if expected and _looks_like_placeholder(expected):
            result["status"] = REJECTED
            result["verification_note"] = "la preuve est un texte d'exemple, pas une donnée réelle"
            verified.append(result)
            continue

        tool_name = result["source_tool"]
        collector = tools.get(tool_name)
        if collector is None:
            result["status"] = UNCERTAIN
            result["verification_note"] = f"collecteur {tool_name} indisponible pour contre-mesure"
            verified.append(result)
            continue

        if tool_name not in remeasured:
            remeasured[tool_name] = collector(url)
        counter_measure = remeasured[tool_name]

        supported = _support(result.get("check", {}), counter_measure)
        if supported is True:
            result["status"] = CONFIRMED
            result["evidence"] = list(dict.fromkeys(result["evidence"] + [counter_measure["evidence"]]))
            result["verification_note"] = "constat retrouvé par une seconde mesure indépendante"
        elif supported is False:
            result["status"] = REJECTED
            result["verification_note"] = "la contre-mesure contredit le constat"
        else:
            result["status"] = UNCERTAIN
            result["verification_note"] = (
                counter_measure.get("error") or "contre-mesure indéterminable"
            )
        verified.append(result)

    return verified


def ai_adjudicate(
    claims: List[Dict[str, Any]],
    llm_client: Any | None = None,
) -> List[Dict[str, Any]]:
    """Soumet les constats confirmés à un modèle qui ne peut que les dégrader."""
    confirmed = [claim for claim in claims if claim.get("status") == CONFIRMED]
    if not confirmed:
        return claims

    try:
        client = llm_client
        if client is None:
            from cv_generator.ai_agents import CVLLMClient

            client = CVLLMClient()
        result = client.complete_json(
            agent_name="company_verifier",
            system_prompt=SYSTEM_PROMPT_PATH.read_text(encoding="utf-8"),
            payload={
                "constats_a_refuter": [
                    {
                        "id": claim["id"],
                        "claim": claim["claim"],
                        "evidence": claim["evidence"],
                        "source_tool": claim["source_tool"],
                    }
                    for claim in confirmed
                ]
            },
        )
        data = getattr(result, "data", result) or {}
    except Exception as exc:  # noqa: BLE001 - l'indisponibilité IA ne doit rien casser
        for claim in claims:
            if claim.get("status") == CONFIRMED:
                claim["ai_review"] = f"indisponible: {type(exc).__name__}"
        return claims

    verdicts = data.get("verdicts")
    verdicts = verdicts if isinstance(verdicts, list) else []
    downgrades = {
        str(item.get("id")): item
        for item in verdicts
        if isinstance(item, dict) and str(item.get("status")) in {UNCERTAIN, REJECTED}
    }

    for claim in claims:
        if claim.get("status") != CONFIRMED:
            continue
        verdict = downgrades.get(claim["id"])
        if verdict is None:
            claim["ai_review"] = "maintenu"
            continue
        # Dégradation uniquement. Aucun verdict ne peut accorder CONFIRMED.
        claim["status"] = str(verdict["status"])
        claim["ai_review"] = str(verdict.get("raison") or "dégradé par le Vérificateur IA")
    return claims


def run_verification(
    company: Dict[str, Any],
    measurements: Dict[str, Dict[str, Any]],
    url: str,
    collectors: Dict[str, Callable[[str], Dict[str, Any]]] | None = None,
    llm_client: Any | None = None,
    use_ai: bool = True,
) -> List[Dict[str, Any]]:
    """Chaîne complète : constats mécaniques → contre-mesure → dégradation IA."""
    claims = build_claims(company, measurements)
    verified = verify_claims(claims, url, collectors=collectors)
    return ai_adjudicate(verified, llm_client=llm_client) if use_ai else verified


def confirmed_only(claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [claim for claim in claims if claim.get("status") == CONFIRMED]
