"""Voie spontanée : entreprises ciblées → constats vérifiés → dossier de candidature.

Volontairement séparé de `pipeline.py`. Celui-ci fonctionne, il est gros, et le
rendre générique risquerait de casser la voie annonce. Le peu qui se duplique est
dupliqué sciemment.

Aucun envoi. Cette chaîne s'arrête au dossier prêt à valider.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from dotenv import dotenv_values, load_dotenv

load_dotenv()

# Même correctif que `pipeline.py` : un service parent peut transmettre des
# variables déclarées mais vides, que python-dotenv ne remplace pas. Sans cela le
# Vérificateur IA se croit indisponible alors que la clé est bien dans `.env`.
for _key, _value in dotenv_values().items():
    if _value and not os.getenv(_key):
        os.environ[_key] = _value

import yaml

from applications import build_application_package
from company_analysis.collectors import COLLECTORS, normalize_domain
from company_analysis.verifier import CONFIRMED, run_verification
from opportunity import build_opportunity
from prospectors import CSVProspector, load_targeting_criteria, target_title_for

CACHE_PATH = Path("data/companies_cache.json")
CRITERIA_PATH = Path("config/criteria.yaml")

# Collecteurs joués sur chaque entreprise, dans cet ordre.
FACT_COLLECTORS = (
    "check_http",
    "inspect_metadata",
    "detect_stack",
    "find_careers_signals",
    "extract_public_contact",
)


def load_user_profile(path: str | Path = CRITERIA_PATH) -> Dict[str, Any]:
    """Le bloc user_profile de criteria.yaml reste valable pour la voie spontanée."""
    criteria_path = Path(path)
    if not criteria_path.exists():
        return {}
    loaded = yaml.safe_load(criteria_path.read_text(encoding="utf-8")) or {}
    profile = loaded.get("user_profile") if isinstance(loaded, dict) else None
    return profile if isinstance(profile, dict) else {}


def collect_facts(url: str) -> Dict[str, Dict[str, Any]]:
    """Joue les collecteurs déterministes sur une entreprise."""
    return {name: COLLECTORS[name](url) for name in FACT_COLLECTORS}


def analyse_company(
    company: Dict[str, Any],
    criteria: Dict[str, Any],
    use_ai: bool = True,
) -> Dict[str, Any]:
    """Mesure, vérifie et compose. Retourne l'opportunité ou le motif du refus."""
    name = str(company.get("nom") or "").strip()
    url = str(company.get("site") or "").strip()
    domain = normalize_domain(url)

    reachability = COLLECTORS["check_http"](url)
    if reachability.get("error"):
        return {
            "company": name,
            "url": url,
            "domain": domain["value"].get("domain"),
            "opportunity": None,
            "refusal": f"site injoignable : {reachability['error']}",
            "claims": [],
        }

    measurements = collect_facts(url)
    claims = run_verification(company, measurements, url, use_ai=use_ai)
    target_title = target_title_for(company, criteria)
    opportunity = build_opportunity(company, claims, target_title) if target_title else None

    if not target_title:
        refusal = "aucun poste visé déclaré pour ce type de structure dans companies.yaml"
    elif opportunity is None:
        refusal = "aucun constat CONFIRMED exploitable : rien à affirmer sur cette structure"
    else:
        refusal = ""

    return {
        "company": name,
        "url": url,
        "domain": domain["value"].get("domain"),
        "opportunity": opportunity,
        "refusal": refusal,
        "claims": claims,
        "measurements": measurements,
    }


def run_spontaneous_search(
    limit: int | None = None,
    use_ai: bool = True,
    csv_path: str | Path | None = None,
    cache_path: str | Path = CACHE_PATH,
) -> List[Dict[str, Any]]:
    """Prospecte, mesure et vérifie. Ne produit aucun document, n'envoie rien."""
    criteria = load_targeting_criteria()
    prospector = CSVProspector(csv_path) if csv_path else CSVProspector()
    companies = prospector.find(criteria)
    if limit is not None:
        companies = companies[:limit]

    results = [analyse_company(company, criteria, use_ai=use_ai) for company in companies]

    cache_file = Path(cache_path)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return results


def prepare_application(
    result: Dict[str, Any],
    user_profile: Dict[str, Any] | None = None,
    with_cv: bool = True,
) -> Dict[str, Any]:
    """Produit le dossier local. Réutilise la chaîne de la voie annonce telle quelle."""
    opportunity = result.get("opportunity")
    if not opportunity:
        raise ValueError(
            f"{result.get('company') or 'Cette structure'} : {result.get('refusal') or 'rien de vérifié'}"
        )

    package = build_application_package(
        opportunity,
        user_profile=user_profile if user_profile is not None else load_user_profile(),
    )

    payload: Dict[str, Any] = {
        "company": opportunity["company"],
        "title": opportunity["title"],
        "directory": package.directory,
        "recommended_cv": package.recommended_cv.cv_id,
        "confirmed_findings": len(opportunity["findings"]),
        "files": {
            "resume": package.resume_path,
            "motivation_letter": package.motivation_letter_path,
            "application_email": package.application_email_path,
            "metadata": package.metadata_path,
        },
    }

    if with_cv:
        from cv_generator import prepare_custom_cv

        cv_result = prepare_custom_cv(opportunity, application_dir=package.directory)
        payload["cv"] = {
            "status": cv_result["status"],
            # Un CV généré n'est pas un CV publiable : seul `published` dit si
            # les fichiers finaux existent.
            "published": cv_result["published"],
            "quality_score": cv_result["quality_score"],
            "ats_score": cv_result["ats_score"],
            "cv_dir": cv_result["cv_dir"],
        }

    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Voie spontanée : prospection, vérification, dossier de candidature."
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--csv", default=None, help="Banc d'essai (défaut : config/companies.csv)")
    parser.add_argument("--no-ai", action="store_true", help="Vérification déterministe seule")
    parser.add_argument(
        "--prepare",
        type=int,
        default=None,
        metavar="N",
        help="Produit le dossier de la Nième entreprise exploitable (1 = la première)",
    )
    parser.add_argument("--no-cv", action="store_true", help="Ne pas générer le CV adapté")
    args = parser.parse_args()

    results = run_spontaneous_search(
        limit=args.limit, use_ai=not args.no_ai, csv_path=args.csv
    )

    for result in results:
        confirmed = sum(1 for claim in result["claims"] if claim.get("status") == CONFIRMED)
        verdict = "refus" if result["opportunity"] is None else "exploitable"
        print(f"[{verdict:<12}] {result['company']} — {confirmed} constat(s) confirmé(s)")
        if result["refusal"]:
            print(f"               motif : {result['refusal']}")

    if args.prepare is not None:
        usable = [result for result in results if result["opportunity"]]
        if args.prepare < 1 or args.prepare > len(usable):
            raise SystemExit(
                f"Entreprise {args.prepare} introuvable. Exploitables : {len(usable)}"
            )
        payload = prepare_application(usable[args.prepare - 1], with_cv=not args.no_cv)
        print()
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
