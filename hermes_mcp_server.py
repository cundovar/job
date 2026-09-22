#!/usr/bin/env python3
"""
Minimal MCP server exposing job-search commands to Hermes.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict

from applications import ApplicationTracker, build_application_package
from hermes_commands.company_prepare import format_preparation, prepare_numbered_application
from hermes_commands.company_top import format_company_list, load_cached_companies
from hermes_commands.utils import format_job_list, load_cached_jobs, ranked_jobs
from pipeline import run_job_search, load_criteria
from pipeline_spontaneous import run_spontaneous_search


def _tool_result(text: str) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _capture(fn: Callable[[], str]) -> Dict[str, Any]:
    # stdout est aussi détourné que stderr : sur un MCP stdio, stdout *est* le
    # canal JSON-RPC. Un seul print() dans le code importé (il y en a des dizaines,
    # dont hermes_commands/company_prepare.py) corrompt la trame et tue la
    # connexion — panne qu'on a mise sur le compte d'un timeout.
    stderr = io.StringIO()
    stdout = io.StringIO()
    try:
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
            return _tool_result(fn())
    except Exception as exc:
        details = "\n".join(part for part in (stdout.getvalue().strip(), stderr.getvalue().strip()) if part)
        message = f"Erreur job-search: {exc}"
        if details:
            message += f"\n\nDetails:\n{details}"
        return {"isError": True, "content": [{"type": "text", "text": message}]}


def job_status(_: Dict[str, Any]) -> str:
    jobs = load_cached_jobs()
    postuler = sum(1 for job in jobs if job.get("ai_analysis", {}).get("recommandation") == "POSTULER")
    peut_etre = sum(1 for job in jobs if job.get("ai_analysis", {}).get("recommandation") == "PEUT-ÊTRE")
    passer = sum(1 for job in jobs if job.get("ai_analysis", {}).get("recommandation") == "PASSER")
    return "\n".join(
        [
            "Statut recherche emploi",
            "",
            f"Offres en cache : {len(jobs)}",
            f"POSTULER : {postuler}",
            f"PEUT-ETRE : {peut_etre}",
            f"PASSER : {passer}",
        ]
    )


def job_top(args: Dict[str, Any]) -> str:
    limit = int(args.get("limit", 5))
    jobs = ranked_jobs(load_cached_jobs(), limit=limit)
    return format_job_list(jobs, title=f"Top {len(jobs)} offres")


def job_today(args: Dict[str, Any]) -> str:
    limit = int(args.get("limit", 5))
    send_outputs = bool(args.get("send_outputs", False))
    search_id = args.get("search_id") or None
    result = run_job_search(send_outputs=send_outputs, search_id=search_id)
    stats = result["stats"]
    top_jobs = ranked_jobs(result["jobs"], limit=limit)
    return "\n".join(
        [
            "Recherche du jour terminee.",
            "",
            f"Offres scrapees : {result['all_jobs_count']}",
            f"Offres filtrees : {stats['total']}",
            f"POSTULER : {stats['postuler']}",
            f"PEUT-ETRE : {stats['peut_etre']}",
            f"PASSER : {stats['passer']}",
            "",
            format_job_list(top_jobs, title=f"Top {len(top_jobs)} offres"),
        ]
    )


def job_prepare(args: Dict[str, Any]) -> str:
    number = int(args.get("number", 1))
    limit = int(args.get("limit", 20))
    jobs = ranked_jobs(load_cached_jobs(), limit=limit)
    if number < 1 or number > len(jobs):
        raise ValueError(f"Offre {number} introuvable. Offres disponibles: {len(jobs)}")
    job = jobs[number - 1]
    criteria = load_criteria()
    package = build_application_package(job, user_profile=criteria.get("user_profile", {}))
    return "\n".join(
        [
            "Candidature preparee.",
            "",
            f"Offre : {job.get('title', 'Poste non renseigne')} - {job.get('company', 'Entreprise non renseignee')}",
            f"Score : {job.get('score', 'Non renseigne')}/100",
            f"Variante CV : {package.recommended_cv.cv_name} ({package.recommended_cv.cv_id})",
            "",
            "Documents generes :",
            f"- {package.resume_path}",
            f"- {package.cv_recommendation_path}",
            f"- {package.motivation_letter_path}",
            f"- {package.application_email_path}",
            f"- {package.metadata_path}",
        ]
    )


def job_relance(args: Dict[str, Any]) -> str:
    tracker_path = str(args.get("tracker", "data/applications_tracker.json"))
    due = ApplicationTracker(tracker_path).due_followups()
    if not due:
        return "Aucune relance a faire aujourd'hui."

    lines = ["Relances a faire", ""]
    for index, record in enumerate(due, start=1):
        lines.extend(
            [
                f"{index}. {record.get('job_title', 'Poste non renseigne')} - {record.get('company', 'Entreprise non renseignee')}",
                f"Postule le : {record.get('applied_at', 'Non renseigne')}",
                f"Relance prevue : {record.get('follow_up_at', 'Non renseignee')}",
                f"URL : {record.get('url', 'Non renseignee')}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def company_top(args: Dict[str, Any]) -> str:
    limit = args.get("limit")
    limit = int(limit) if limit is not None else None
    refresh = bool(args.get("refresh", False))
    postal_code = str(args.get("postal_code") or "").strip() or None

    results = load_cached_companies()
    if refresh or not results or postal_code:
        # Une demande zonée repasse par le banc d'essai : le cache ne sait pas de
        # quelle zone il vient, le filtrer donnerait une réponse non vérifiée.
        results = run_spontaneous_search(limit=limit, postal_code=postal_code)
    elif limit is not None:
        results = results[:limit]

    return format_company_list(
        results, title=f"Prospection spontanee — {len(results)} structure(s)"
    )


def company_prepare(args: Dict[str, Any]) -> str:
    results = load_cached_companies()
    if not results:
        results = run_spontaneous_search()

    payload = prepare_numbered_application(
        int(args.get("number", 1)), results, with_cv=bool(args.get("with_cv", False))
    )
    return format_preparation(payload)


ROOT = Path(__file__).resolve().parent
AGENCIES_PATH = ROOT / "front" / "public" / "data" / "agencies" / "latest.json"


def _job_search_base_url() -> str:
    """URL du backend Node job-search, distincte du gateway Hermes.

    `HERMES_API_URL` désigne le gateway Hermes (chat et runs, port 8642) et ne
    doit jamais servir à joindre Express. Le backend peut être configuré par
    `JOB_SEARCH_API_URL`; sinon son port suit la même source que
    `server/config.js` (`PORT`, puis le `.env` racine, puis 3001).
    """
    explicit = os.getenv("JOB_SEARCH_API_URL")
    if explicit:
        return explicit.rstrip("/")
    port = os.getenv("PORT")
    if not port:
        env_file = ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                key, _, value = line.strip().partition("=")
                if key.strip() == "PORT":
                    port = value.strip().strip("\"'")
                    break
    return f"http://localhost:{port or 3001}"


# Le serveur Node possède déjà la file asynchrone et le lancement du script de
# prospection. Le MCP l'appelle plutôt que de dupliquer une seconde file, qui
# écrirait latest.json en concurrence de la première.
JOB_SEARCH_API = _job_search_base_url()


def _api(method: str, path: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    import urllib.error
    import urllib.request

    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{JOB_SEARCH_API}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise ValueError(f"Backend job-search a répondu {exc.code} : {body}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(
            f"Backend job-search injoignable sur {JOB_SEARCH_API} ({exc.reason}). "
            "Démarre-le avec `cd server && npm start`."
        ) from exc


def agency_search(args: Dict[str, Any]) -> str:
    city = str(args.get("city") or "").strip()
    departement = str(args.get("departement") or "").strip()
    zone = str(args.get("zone") or "").strip()
    radius_m = args.get("radius_m")

    if city and zone:
        raise ValueError(
            "city et zone sont exclusifs : zone rejoue un preréglage historique "
            "(ile-de-france, paris-20, paris-19, ouest-paris), city resout une "
            "commune reelle. Choisis l'un des deux."
        )

    payload: Dict[str, Any] = {}
    if city:
        payload["city"] = city
        if departement:
            payload["departement"] = departement
        perimetre = f"Ville : {city}" + (f" (departement {departement})" if departement else "")
    else:
        payload["zone"] = zone or "ile-de-france"
        perimetre = f"Zone (prereglage) : {payload['zone']}"
    if radius_m is not None:
        payload["radius_m"] = int(radius_m)

    response = _api("POST", "/api/agencies/search", payload)
    task_id = response.get("task_id")
    return "\n".join(
        [
            "Prospection lancee (traitement long, plusieurs minutes).",
            "",
            perimetre,
            f"Rayon : {radius_m} m" if radius_m is not None else "Rayon : aucun filtre de distance",
            f"task_id : {task_id}",
            "",
            f"Suivre avec agency_status(task_id=\"{task_id}\").",
            "Les resultats n'existent qu'une fois la tache terminee : ne rien",
            "annoncer avant, et ne jamais completer la liste de memoire.",
        ]
    )


def agency_status(args: Dict[str, Any]) -> str:
    task_id = str(args.get("task_id") or "").strip()
    if not task_id:
        raise ValueError("task_id manquant : il est renvoye par agency_search.")

    task = _api("GET", f"/api/agencies/search/status/{task_id}")
    resolved = task.get("resolved_city") or {}
    lines = [
        f"Prospection {task_id}",
        "",
        f"Etat : {task.get('state')}",
    ]
    if task.get("city"):
        # La ville resolue est celle qui a servi : si elle differe de la demande,
        # c'est la resolution qui l'a tranchee, et ca doit se voir.
        lines.append(f"Ville demandee : {task.get('city')}")
        if resolved:
            lines.append(
                f"Ville resolue : {resolved.get('name')} (INSEE {resolved.get('insee')}, "
                f"{', '.join(resolved.get('postal_codes') or []) or 'codes postaux inconnus'})"
            )
    else:
        lines.append(f"Zone : {task.get('zone')}")
    lines += [
        f"Rayon : {task.get('radius_m') or 'aucun'}",
        f"En file depuis : {task.get('queued_at')}",
    ]
    steps = task.get("steps") or []
    if steps:
        # Les etapes disent ou en est la passe : sans elles, un run lent et un run
        # bloque se ressemblent, et on relance une prospection deja en cours.
        lines += ["", "Etapes :"]
        for step in steps:
            duree = step.get("duration_ms")
            volumes = " · ".join(f"{k} {v}" for k, v in (step.get("volumes") or {}).items())
            lines.append(
                f"  - {step.get('step')} : "
                + (f"{duree} ms" if duree is not None else "en cours")
                + (f" ({volumes})" if volumes else "")
            )
    if task.get("error"):
        lines += ["", f"Erreur : {task['error']}"]
    result = task.get("result") or {}
    if result:
        lines += ["", f"Agences retenues : {result.get('total')}", f"Domaines scannes : {result.get('scanned_domains')}"]
        perimeter = result.get("perimeter") or {}
        if perimeter:
            lines.append(
                f"Dans {perimeter.get('city')} (adresse lue ou registre) : {perimeter.get('verifie')} · "
                f"mention seule : {perimeter.get('mention_seule')} · "
                f"sans lien verifiable : {perimeter.get('sans_lien')}"
            )
        radius = result.get("radius")
        if radius:
            lines.append(
                f"Dans le rayon : {radius.get('inside')} · position approximative : "
                f"{radius.get('approximate')} · hors rayon : {radius.get('outside')} · "
                f"position inconnue : {radius.get('unknown')}"
            )
        search_id = task.get("search_id")
        lines.append("")
        # Le search_id est la seule facon de relire CETTE passe : sans lui,
        # agency_list ouvrirait « la plus recente », qui peut etre une autre ville.
        lines.append(f"search_id : {search_id or 'aucun (passe sans resultat)'}")
        if search_id:
            lines.append(f"Lire la liste avec agency_list(search_id=\"{search_id}\").")
        else:
            lines.append("Aucune recherche a relire : relance agency_search.")
    return "\n".join(lines)


def agency_list(args: Dict[str, Any]) -> str:
    limit = args.get("limit")
    limit = int(limit) if limit is not None else None
    postal_code = str(args.get("postal_code") or "").strip()
    search_id = str(args.get("search_id") or "").strip()

    if search_id:
        # Relire la passe nommee, jamais « la plus recente » : entre deux
        # prospections, latest.json peut appartenir a une autre ville, et la
        # liste se relirait comme celle qu'on vient de lancer.
        payload = _api("GET", f"/api/agencies/searches/{search_id}")
    else:
        if not AGENCIES_PATH.exists():
            raise ValueError(
                f"Aucune prospection enregistree ({AGENCIES_PATH} absent). "
                "Lance agency_search d'abord. Ne pas citer d'agences de memoire."
            )
        payload = json.loads(AGENCIES_PATH.read_text(encoding="utf-8"))
    agencies = payload.get("agencies") or []

    # Nommer la passe lue, pas « la derniere » : quand deux villes s'enchainent,
    # « la derniere prospection » ne dit pas laquelle on a sous les yeux.
    read_id = payload.get("search_id") or search_id
    city = payload.get("city") or {}
    origin = f"recherche {read_id}" if read_id else f"fichier {AGENCIES_PATH.name}"
    perimetre = city.get("label") or payload.get("zone_label") or payload.get("zone") or "perimetre inconnu"

    if postal_code:
        matching = [
            agency
            for agency in agencies
            if str(agency.get("postal_code") or "").startswith(postal_code)
        ]
        if not matching:
            # Dire ce qui existe plutôt que renvoyer une liste vide : c'est ce
            # vide, pris pour « il n'y a rien », qui a fait inventer des agences.
            known = sorted({str(a.get("postal_code") or "?") for a in agencies})
            raise ValueError(
                f"Aucune agence en {postal_code} dans la {origin} "
                f"({perimetre}, {payload.get('generated_at')}). "
                f"Codes postaux presents : {', '.join(known)}. "
                "Relance agency_search pour couvrir cette zone."
            )
        agencies = matching

    if limit is not None:
        agencies = agencies[:limit]

    lines = [
        f"Agences prospectees — {len(agencies)} resultat(s)",
        f"Passe du {payload.get('generated_at')} · {perimetre} · {origin}",
        "",
    ]
    for index, agency in enumerate(agencies, start=1):
        lines.append(f"{index}. {agency.get('name')}")
        lines.append(f"   Site : {agency.get('website') or 'non trouve'}")
        # L'adresse et sa provenance sont affichees ensemble : une position
        # « ville/arr (~centre) » n'est pas une adresse et doit se voir comme telle.
        address = agency.get("address")
        if address:
            postal = agency.get("postal_code")
            lines.append(f"   Adresse : {address}{f' — {postal}' if postal else ''}")
            lines.append(f"   Source de l'adresse : {agency.get('how') or agency.get('address_source')}")
        else:
            lines.append("   Adresse : non publiee sur le site (aucune adresse lue)")
        distance = agency.get("distance_m")
        lines.append(
            f"   Distance : {distance} m" if distance is not None else "   Distance : non mesurable"
        )
        # Le lien a la ville se dit avec sa preuve : « mention » veut dire que le
        # nom apparait dans une page, ce qui n'etablit aucune implantation.
        if agency.get("city_match"):
            lines.append(
                f"   Perimetre {agency.get('city') or ''} : {agency['city_match']}"
                f" — {agency.get('city_match_evidence') or 'sans preuve'}"
            )
        lines.append("")
    return "\n".join(lines).rstrip()


# RÈGLE DE SÉCURITÉ : ce dictionnaire est la liste des permissions de Hermes.
# Il ne contient aucun outil d'envoi, et ne doit jamais en contenir. Préparer un
# dossier, oui ; l'expédier, jamais. La garantie est ici, pas dans un prompt.
#
# Les descriptions nomment toutes ce qu'elles cherchent : une **annonce** (offre
# d'emploi publiee) ou une **entreprise/agence** (structure a demarcher). Les
# anciennes formulations — « Lance la recherche d'emploi du jour » face a
# « Affiche les entreprises ciblees » — ne disaient a aucun agent laquelle sert a
# trouver des agences ; d'ou des recherches d'annonces lancees en boucle, puis des
# agences inventees pour combler le vide.

# ── Agency Scout (V3 : Google Places + 1 appel IA par site) ──────────────────
# Appel direct du module Python : pas de dépendance au backend Node.


def scout_scan(args: Dict[str, Any]) -> str:
    from agency_scout.core import start_background
    cli = ["scan"]
    if args.get("lat") is not None and args.get("lng") is not None:
        cli += ["--lat", str(float(args["lat"])), "--lng", str(float(args["lng"]))]
    if args.get("radius_m"):
        cli += ["--rayon", str(int(args["radius_m"]))]
    for q in args.get("queries") or []:
        cli += ["--requete", str(q)]
    for c in args.get("cp") or []:
        cli += ["--cp", str(c)]
    if args.get("reanalyse"):
        cli.append("--reanalyse")
    info = start_background(cli)
    return (f"Scan agences lancé en arrière-plan (pid {info['pid']}). Compter 1 à 3 minutes, "
            "puis appeler scout_list. Si scout_list montre encore 'running', attendre.")


def scout_list(args: Dict[str, Any]) -> str:
    from agency_scout.core import list_agencies
    data = list_agencies(args.get("categorie"), int(args.get("min_score", 0)))
    limit = int(args.get("limit", 15))
    head = []
    if data["running"]:
        head.append(f"⏳ Scan en cours depuis {data['running']['since']} — résultats partiels.")
    last = data["last_scan"]
    last_scope = (f"codes postaux {', '.join(last.get('postal_codes') or [])}"
                  if last and last.get("postal_codes")
                  else (f"rayon {last['radius_m']} m" if last else ""))
    head.append(f"Dernier scan : {last['finished_at']} ({last['places']} lieux, {last_scope})"
                if last else "Aucun scan terminé pour l'instant.")
    head.append(f"Quota Google Places : {data['places_calls_this_month']}/{data['places_monthly_cap']} appels ce mois.")
    rows = data["agencies"]
    if not rows:
        return "\n".join(head + ["", "Aucune agence en base pour ces filtres."])
    lines = []
    for i, a in enumerate(rows[:limit], 1):
        verdict = (f"{a['categorie']} {a['score']}/10" if a["categorie"]
                   else (a["error"] or "pas de site web" if not a["website"] else a["error"] or "non analysé"))
        flag = "" if a["preuve_ok"] in (None, 1) else " ⚠ preuve non retrouvée dans le site"
        lines.append(f"{i}. {a['name']} — {verdict}{flag}\n   {a['address']} · {a['distance_m']} m · {a['website'] or '—'}"
                     + (f"\n   {a['resume']}" if a["resume"] else ""))
    return "\n".join(head + [f"", f"{len(rows)} structures (affichées : {min(limit, len(rows))})", ""] + lines)

TOOLS: Dict[str, Dict[str, Any]] = {
    "scout_scan": {
        "description": (
            "ENTREPRISES/AGENCES — Lance un scan d'agences web et d'organismes de formation "
            "(Google Places + analyse IA de chaque site). Rend la main tout de suite ; "
            "les résultats se lisent ensuite avec scout_list. Deux modes : passer cp "
            "(ex. [\"75020\"]) pour un arrondissement strict — l'adresse Google décide, "
            "le rayon ne filtre plus ; sinon rayon 3000 m autour de Paris 20e. "
            "Pour une autre ville, passer lat/lng de son centre."
        ),
        "handler": scout_scan,
        "inputSchema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lng": {"type": "number"},
                "radius_m": {"type": "integer", "description": "Rayon en mètres (défaut 3000, max 50000) — ignoré si cp est fourni."},
                "cp": {"type": "array", "items": {"type": "string"},
                       "description": "Codes postaux imposés (ex. [\"75020\"]) : mode arrondissement strict, l'adresse Google décide."},
                "queries": {"type": "array", "items": {"type": "string"},
                            "description": "Requêtes Google Places ; défaut : agence web, agence digitale, création site internet, organisme de formation numérique."},
                "reanalyse": {"type": "boolean", "description": "Refaire l'IA même si le site n'a pas changé."},
            },
            "additionalProperties": False,
        },
    },
    "scout_list": {
        "description": (
            "ENTREPRISES/AGENCES — Liste les agences trouvées par scout_scan, triées par score "
            "d'adéquation IA puis distance. Lecture de base, instantané. Chaque ligne donne "
            "catégorie, score /10, adresse et site tels que fournis par Google."
        ),
        "handler": scout_list,
        "inputSchema": {
            "type": "object",
            "properties": {
                "categorie": {"type": "string", "enum": ["agence", "formation", "autre"]},
                "min_score": {"type": "integer"},
                "limit": {"type": "integer"},
            },
            "additionalProperties": False,
        },
    },
    "job_status": {
        "description": (
            "ANNONCES — Compte les offres d'emploi deja en cache par recommandation "
            "(POSTULER / PEUT-ETRE / PASSER). Lecture de cache, instantane. "
            "Ne cherche aucune entreprise."
        ),
        "handler": job_status,
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "job_top": {
        "description": (
            "ANNONCES — Affiche les meilleures offres d'emploi deja en cache. "
            "Lecture de cache, instantane. Ne cherche aucune entreprise ni agence."
        ),
        "handler": job_top,
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 5}},
            "additionalProperties": False,
        },
    },
    "job_today": {
        "description": (
            "ANNONCES — Lance le scraping des offres d'emploi publiees du jour, puis "
            "les filtre et les note. Traitement long (plusieurs minutes). "
            "Ne decouvre AUCUNE entreprise ni agence : pour chercher des agences, "
            "utiliser agency_search."
        ),
        "handler": job_today,
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 5},
                "send_outputs": {"type": "boolean", "default": False},
                "search_id": {
                    "type": "string",
                    "description": (
                        "Identifiant explicite de la session de recherche a archiver "
                        "(front/public/data/<search_id>/). Par defaut : la date du jour."
                    ),
                },
            },
            "additionalProperties": False,
        },
    },
    "job_prepare": {
        "description": (
            "ANNONCES — Prepare le dossier de candidature pour une offre du classement "
            "(CV recommande, lettre, email). N'envoie rien."
        ),
        "handler": job_prepare,
        "inputSchema": {
            "type": "object",
            "properties": {
                "number": {"type": "integer", "default": 1},
                "limit": {"type": "integer", "default": 20},
            },
            "additionalProperties": False,
        },
    },
    "job_relance": {
        "description": (
            "ANNONCES — Liste les candidatures deja envoyees dont la relance est due "
            "aujourd'hui. Lecture du tracker, instantane."
        ),
        "handler": job_relance,
        "inputSchema": {
            "type": "object",
            "properties": {"tracker": {"type": "string", "default": "data/applications_tracker.json"}},
            "additionalProperties": False,
        },
    },
    "company_top": {
        "description": (
            "ENTREPRISES/AGENCES — Mesure les structures du banc d'essai tenu a la main "
            "(config/companies.csv) et affiche pour chacune son adresse, son URL et ses "
            "constats verifies. Ne decouvre rien de nouveau : c'est agency_search qui "
            "cherche. Lit le cache, sauf refresh=true ou postal_code (traitement long)."
        ),
        "handler": company_top,
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
                "refresh": {"type": "boolean", "default": False},
                "postal_code": {
                    "type": "string",
                    "description": (
                        "Ne garder que les structures de cette zone, ex. 75020 ou 75. "
                        "Force une nouvelle mesure. Une zone que personne ne porte leve "
                        "une erreur au lieu de renvoyer une liste vide."
                    ),
                },
            },
            "additionalProperties": False,
        },
    },
    "company_prepare": {
        "description": (
            "ENTREPRISES/AGENCES — Prepare le dossier de candidature spontanee pour une "
            "structure exploitable de company_top. N'envoie rien. with_cv=true ajoute la "
            "generation du CV adapte, qui prend plusieurs minutes."
        ),
        "handler": company_prepare,
        "inputSchema": {
            "type": "object",
            "properties": {
                "number": {"type": "integer", "default": 1},
                # Defaut a False : c'est la generation du CV (LLM + tours de revision)
                # qui faisait exploser le budget de 120 s et couper la connexion MCP,
                # pas la mesure. Le CV reste accessible, mais sur demande explicite.
                "with_cv": {"type": "boolean", "default": False},
            },
            "additionalProperties": False,
        },
    },
    "agency_search": {
        "description": (
            "ENTREPRISES/AGENCES — Lance une prospection qui DECOUVRE de nouvelles agences "
            "web (moteurs de recherche, annuaires), releve leur adresse sur leur site et "
            "calcule leur distance. C'est l'outil a utiliser pour « trouve-moi des agences "
            "a Montreuil » ou « dans le 20e ». Donner 'city' pour n'importe quelle commune "
            "francaise ; 'zone' ne sert qu'aux quatre prereglages historiques. Traitement "
            "long : repond immediatement avec un task_id, suivre avec agency_status, lire "
            "les resultats avec agency_list(search_id=...)."
        ),
        "handler": agency_search,
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": (
                        "Nom de la commune a prospecter, ex. Montreuil, Lille, Quimper. "
                        "Toute commune francaise est acceptee : la liste des zones n'est "
                        "pas la liste des villes supportees. Exclusif avec 'zone'."
                    ),
                },
                "departement": {
                    "type": "string",
                    "description": (
                        "Code du departement, ex. 93, 59, 2A. Obligatoire quand plusieurs "
                        "communes portent le meme nom (Montreuil existe en 93, 85 et 28)."
                    ),
                },
                "zone": {
                    "type": "string",
                    "description": (
                        "Prereglage historique : ile-de-france, paris-20, paris-19, "
                        "ouest-paris. Exclusif avec 'city' ; preferer 'city'."
                    ),
                },
                "radius_m": {
                    "type": "integer",
                    "description": (
                        "Ne garder que les agences dont l'adresse LUE tombe sous ce rayon "
                        "(en metres) autour de l'adresse de reference. Une position deduite "
                        "du centre d'un arrondissement n'y entre jamais."
                    ),
                },
            },
            "additionalProperties": False,
        },
    },
    "agency_status": {
        "description": (
            "ENTREPRISES/AGENCES — Donne l'avancement d'une prospection lancee par "
            "agency_search. Instantane. Detaille les etapes (resolution de la ville, "
            "registre, decouverte web, crawl, geocodage, IA, publication) et rend le "
            "search_id a passer a agency_list. Tant que l'etat n'est pas 'completed', "
            "aucun resultat n'existe encore."
        ),
        "handler": agency_status,
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
            "additionalProperties": False,
        },
    },
    "agency_list": {
        "description": (
            "ENTREPRISES/AGENCES — Lit une prospection enregistree et affiche chaque "
            "agence avec son adresse, son code postal, sa distance et la SOURCE de l'adresse. "
            "Lecture de fichier, instantane. Donner le 'search_id' rendu par agency_status : "
            "sans lui, l'outil ouvre la derniere passe publiee, qui peut porter sur une autre "
            "ville. Si aucune agence ne correspond a la zone demandee, leve une erreur "
            "explicite plutot que de renvoyer une liste vide."
        ),
        "handler": agency_list,
        "inputSchema": {
            "type": "object",
            "properties": {
                "search_id": {
                    "type": "string",
                    "description": (
                        "Identifiant de la passe a relire, rendu par agency_status. "
                        "Omis, l'outil lit la derniere passe publiee."
                    ),
                },
                "limit": {"type": "integer"},
                "postal_code": {
                    "type": "string",
                    "description": "Ne garder que les agences de cette zone, ex. 75020 ou 75.",
                },
            },
            "additionalProperties": False,
        },
    },
}


def _debug(message: str) -> None:
    with open("/tmp/job-search-mcp.log", "a", encoding="utf-8") as f:
        f.write(message + "\n")


def _handle(request: Dict[str, Any]) -> Dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")

    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "job-search", "version": "1.0.0"},
            },
        }
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": name,
                        "description": spec["description"],
                        "inputSchema": spec["inputSchema"],
                    }
                    for name, spec in TOOLS.items()
                ]
            },
        }
    if method == "tools/call":
        params = request.get("params", {})
        name = params.get("name")
        arguments = params.get("arguments", {}) or {}
        if name not in TOOLS:
            result = {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {name}"}]}
        else:
            result = _capture(lambda: TOOLS[name]["handler"](arguments))
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> None:
    os.chdir(Path(__file__).resolve().parent)
    _debug("server-start")
    while True:
        headers = {}
        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                _debug("stdin-eof")
                return
            line = line.decode("utf-8").strip()
            if not line:
                break
            # Support both standard Content-Length framed MCP messages and
            # newline-delimited JSON-RPC messages used by some clients/tests.
            if line.startswith("{"):
                _debug(f"jsonline={line}")
                response = _handle(json.loads(line))
                if response is not None:
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
                    _debug(f"jsonline-response={response.get('id')}")
                headers = {}
                break
            key, _, value = line.partition(":")
            headers[key.lower()] = value.strip()

        _debug(f"headers={headers}")
        content_length = int(headers.get("content-length", "0"))
        if content_length <= 0:
            continue

        body = sys.stdin.buffer.read(content_length).decode("utf-8")
        _debug(f"body={body}")
        response = _handle(json.loads(body))
        if response is not None:
            payload = json.dumps(response).encode("utf-8")
            sys.stdout.buffer.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("utf-8"))
            sys.stdout.buffer.write(payload)
            sys.stdout.buffer.flush()
            _debug(f"response={response.get('id')} {response.get('result', response.get('error'))}")


if __name__ == "__main__":
    main()
