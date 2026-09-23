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

# Chemins ancrés au dépôt, pas au répertoire courant : lancé depuis ailleurs
# (service systemd, MCP), le pipeline écrivait son cache dans un `data/` créé au
# hasard du cwd, et company_top ne le retrouvait jamais.
ROOT = Path(__file__).resolve().parent
CACHE_PATH = ROOT / "data" / "companies_cache.json"
CRITERIA_PATH = ROOT / "config" / "criteria.yaml"

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


def _scout_structure_profile(domain: str | None) -> Dict[str, Any]:
    """Profil auto-déclaré du scout (catégorie, résumé, preuve), s'il existe.

    Import paresseux et silencieux : la voie spontanée doit fonctionner même
    quand le module scout ou sa base sont absents. Le profil est un plus de
    contexte pour les rédacteurs, jamais une dépendance.
    """
    try:
        from agency_scout.core import structure_profile

        return structure_profile(domain or "")
    except Exception:
        return {}


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
        # Contexte « qu'est-ce que cette structure » (organisme de formation ?
        # agence de production ?) pour la lettre et le mail : auto-description
        # du site relevée par le scout, jamais une déduction.
        opportunity["structure_profile"] = _scout_structure_profile(
            domain["value"].get("domain")
        )

    return {
        "company": name,
        "url": url,
        "domain": domain["value"].get("domain"),
        "opportunity": opportunity,
        "refusal": refusal,
        "claims": claims,
        "measurements": measurements,
    }


def filter_by_postal_code(
    companies: List[Dict[str, Any]], postal_code: str
) -> List[Dict[str, Any]]:
    """Ne garde que les entreprises dont le code postal commence par `postal_code`.

    Une entreprise sans code postal relevé est écartée : on ne sait pas où elle
    est, et deviner depuis la colonne `ville` produirait une localisation qui n'a
    jamais été vérifiée. Une zone que personne ne porte lève une erreur plutôt que
    de renvoyer une liste vide qui passerait pour « aucune agence par ici ».
    """
    prefix = postal_code.strip()
    if not prefix.isdigit():
        raise ValueError(
            f"Code postal invalide : « {postal_code} ». Attendu un préfixe numérique, "
            "par exemple 75020 ou 75."
        )

    known = {
        str(company.get("code_postal") or "").strip()
        for company in companies
        if str(company.get("code_postal") or "").strip()
    }
    if not any(code.startswith(prefix) for code in known):
        raise ValueError(
            f"Aucune entreprise du banc d'essai n'est en {prefix}. "
            f"Codes postaux connus : {', '.join(sorted(known)) or 'aucun'}. "
            "Ajoute les entreprises à config/companies.csv avec leur adresse relevée."
        )

    return [
        company
        for company in companies
        if str(company.get("code_postal") or "").strip().startswith(prefix)
    ]


def run_spontaneous_search(
    limit: int | None = None,
    use_ai: bool = True,
    csv_path: str | Path | None = None,
    cache_path: str | Path = CACHE_PATH,
    postal_code: str | None = None,
) -> List[Dict[str, Any]]:
    """Prospecte, mesure et vérifie. Ne produit aucun document, n'envoie rien."""
    criteria = load_targeting_criteria()
    prospector = CSVProspector(csv_path) if csv_path else CSVProspector()
    companies = prospector.find(criteria)
    if postal_code:
        companies = filter_by_postal_code(companies, postal_code)
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
        "--code-postal",
        default=None,
        help="Ne garder que les entreprises de cette zone (ex. 75020, ou 75 pour Paris)",
    )
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
        limit=args.limit,
        use_ai=not args.no_ai,
        csv_path=args.csv,
        postal_code=args.code_postal,
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
