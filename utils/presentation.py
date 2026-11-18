"""Présentation d'un dossier : site web affiché ou non, titre de la signature.

Demande Cundo (18/11/2026) : varascundo.com sortait dans toutes les lettres et
tous les mails, et le mail HTML signait « Développeur web & formateur » même
pour un poste d'animateur. Ces deux choix appartiennent au candidat, dossier
par dossier. Ils vivent dans ``job.json`` :

- ``show_website`` (bool) : afficher une ligne « Portfolio : … » ;
- ``website_url`` (str) : le site affiché quand la case est cochée ;
- ``display_title`` (str) : le titre sous le nom dans la signature du mail HTML.

Sans choix explicite, la famille du poste décide (comportement d'avant pour
le développement, rien pour la médiation, l'accueil, la logistique…).

Tout ce module est mécanique : il ne réécrit jamais le texte d'une lettre,
il ajoute, remplace ou retire la seule ligne « Portfolio ».

CLI (utilisée par le serveur) :
    python -m utils.presentation <dossier> --show
    python -m utils.presentation <dossier> --set '<json>'
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict

from cv_generator import rules as candidate_rules

_LOG = logging.getLogger(__name__)

DEFAULT_WEBSITE = "varascundo.com"
#: Sites proposés dans l'interface ; une adresse libre reste possible.
WEBSITE_CHOICES = (
    "varascundo.com",
    "mediateur.varascundo.com",
    "devdoc.varascundo.com",
    "ia.varascundo.com",
)
TITLE_MAX = 120
URL_MAX = 200

#: Familles où le site apparaît par défaut (comportement historique).
_WEBSITE_FAMILIES = frozenset({"developpement", "webmaster", "formation", "autre"})

_DEFAULT_TITLES = {
    "developpement": "Développeur web & formateur — Paris",
    "webmaster": "Développeur web & formateur — Paris",
    "formation": "Formateur web & numérique — Paris",
    "mediation_numerique": "Formateur numérique — Paris",
    "mediation_sociale": "Accueil, animation & formation d'adultes — Paris",
    "accueil": "Accueil & orientation des publics — Paris",
    "logistique": "Paris, Île-de-France",
    "surveillance": "Paris, Île-de-France",
    "autre": "Développeur web & formateur — Paris",
}

_PORTFOLIO_LINE_RE = re.compile(r"^\s*(\*\*)?portfolio(\*\*)?\s*:", re.I)
_SIGNATURE_NAME_RE = re.compile(r"^\s*Facundo Varas(\s*\(Cundo\))?\s*$", re.I)
_URL_RE = re.compile(r"^(https?://)?[\w-]+(\.[\w-]+)+(/[\w./%-]*)?$", re.I)


def _family(job: Dict[str, Any]) -> str:
    family = str((job or {}).get("job_family") or "")
    if family in candidate_rules.JOB_FAMILIES:
        return family
    return "mediation_sociale" if candidate_rules.is_mediation_job(job or {}) else "autre"


def clean_url(value: Any) -> str:
    """Adresse affichable (sans schéma ni / final), ou chaîne vide si invalide."""
    raw = str(value or "").strip()[:URL_MAX]
    if not raw or not _URL_RE.match(raw):
        return ""
    return re.sub(r"^https?://", "", raw, flags=re.I).rstrip("/")


def presentation_for(job: Dict[str, Any]) -> Dict[str, Any]:
    """Réglages effectifs du dossier : choix du candidat, sinon défauts de famille."""
    job = job or {}
    family = _family(job)
    explicit = isinstance(job.get("show_website"), bool)
    show = job["show_website"] if explicit else family in _WEBSITE_FAMILIES
    url = clean_url(job.get("website_url")) or DEFAULT_WEBSITE
    title = str(job.get("display_title") or "").strip()[:TITLE_MAX]
    return {
        "show_website": bool(show),
        "website_url": url,
        "display_title": title or _DEFAULT_TITLES.get(family, _DEFAULT_TITLES["autre"]),
        "explicit": {
            "show_website": explicit,
            "display_title": bool(title),
        },
        "family": family,
        "choices": list(WEBSITE_CHOICES),
    }


def contact_line(presentation: Dict[str, Any]) -> str:
    """Bandeau du PDF de la lettre."""
    parts = ["Paris 20e", "contact@varascundo.com"]
    if presentation.get("show_website"):
        parts.append(presentation.get("website_url") or DEFAULT_WEBSITE)
    return " · ".join(parts)


def apply_website_line(text: str, presentation: Dict[str, Any]) -> str:
    """Ajoute, remplace ou retire la ligne « Portfolio » ; le reste n'est pas touché.

    Site masqué : toute ligne Portfolio disparaît. Site affiché : une ligne
    existante prend l'adresse choisie ; sans ligne, elle est ajoutée sous le
    nom de la signature (ou à la fin s'il n'y a pas de signature reconnue).
    """
    lines = (text or "").splitlines()
    trailing_newline = (text or "").endswith("\n")
    if not presentation.get("show_website"):
        kept = [line for line in lines if not _PORTFOLIO_LINE_RE.match(line)]
        result = "\n".join(kept)
    else:
        line_text = f"Portfolio : {presentation.get('website_url') or DEFAULT_WEBSITE}"
        replaced = False
        out = []
        for line in lines:
            if _PORTFOLIO_LINE_RE.match(line):
                if not replaced:
                    out.append(line_text)
                    replaced = True
                continue
            out.append(line)
        if not replaced:
            names = [i for i, line in enumerate(out) if _SIGNATURE_NAME_RE.match(line)]
            if names:
                out.insert(names[-1] + 1, line_text)
            else:
                while out and not out[-1].strip():
                    out.pop()
                out.append(line_text)
        result = "\n".join(out)
    return result + ("\n" if trailing_newline and not result.endswith("\n") else "")


_BARE_SITE_RE = re.compile(r"(?<![\w.@-])varascundo\.com", re.I)


def hidden_site_mentions(text: str, presentation: Dict[str, Any]) -> bool:
    """Vrai si le site principal est cité dans le corps alors qu'il est masqué.

    Un sous-domaine (mediateur.varascundo.com…) cité comme projet n'est pas
    visé. On avertit, on ne réécrit pas : retirer une phrase inventerait.
    """
    if presentation.get("show_website"):
        return False
    return bool(_BARE_SITE_RE.search(text or ""))


# ── Mise à jour d'un dossier existant ────────────────────────────────────

def _read_json(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def update_dossier_presentation(directory: str | Path, changes: Dict[str, Any]) -> Dict[str, Any]:
    """Enregistre les choix dans job.json et les applique à la lettre et au mail.

    La lettre (markdown puis PDF) et le mail perdent ou gagnent leur ligne
    Portfolio ; le titre ne touche que le mail HTML, rendu à l'envoi. Le
    verrou d'envoi et la chute de l'approbation sont gérés par le serveur
    (hasSendRecord / writeApprovalStatus), seule source de ces règles.
    """
    directory = Path(directory)
    job_path = directory / "job.json"
    if not job_path.is_file():
        raise FileNotFoundError(f"Dossier incomplet (job.json absent) : {directory.name}")
    job = _read_json(job_path)

    if "show_website" in changes:
        if not isinstance(changes["show_website"], bool):
            raise ValueError("show_website doit valoir true ou false.")
        job["show_website"] = changes["show_website"]
    if "website_url" in changes:
        raw = str(changes.get("website_url") or "").strip()
        url = clean_url(raw)
        if raw and not url:
            raise ValueError(f"Adresse de site invalide : {raw[:80]}")
        if url:
            job["website_url"] = url
        else:
            job.pop("website_url", None)
    if "display_title" in changes:
        title = str(changes.get("display_title") or "").strip()[:TITLE_MAX]
        if title:
            job["display_title"] = title
        else:
            job.pop("display_title", None)

    presentation = presentation_for(job)
    _write_json(job_path, job)

    letter_path = directory / "lettre_motivation.md"
    warning = None
    updated = updated_mail = None
    if letter_path.is_file():
        letter = letter_path.read_text(encoding="utf-8")
        updated = apply_website_line(letter, presentation)
        if updated != letter:
            letter_path.write_text(updated, encoding="utf-8")
        if hidden_site_mentions(updated, presentation):
            warning = "La lettre cite encore varascundo.com dans son texte : à corriger à la main avant l'envoi."
        from applications.application_builder import _write_letter_pdf

        _write_letter_pdf(letter_path, directory, job)

    mail_path = directory / "mail_candidature.md"
    if mail_path.is_file():
        mail = mail_path.read_text(encoding="utf-8")
        updated_mail = apply_website_line(mail, presentation)
        if updated_mail != mail:
            mail_path.write_text(updated_mail, encoding="utf-8")

    # Les textes à jour reviennent au front, qui les affiche sans relire l'index.
    return {"ok": True, "presentation": presentation, "warning": warning,
            "lettre": updated, "mail": updated_mail}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) < 2 or args[1] not in {"--show", "--set"}:
        print("Usage : python -m utils.presentation <dossier> --show | --set '<json>'", file=sys.stderr)
        return 2
    directory = Path(args[0])
    try:
        if args[1] == "--show":
            job = _read_json(directory / "job.json")
            result = {"ok": True, "presentation": presentation_for(job)}
        else:
            changes = json.loads(args[2] if len(args) > 2 else "{}")
            if not isinstance(changes, dict):
                raise ValueError("Les changements doivent être un objet JSON.")
            result = update_dossier_presentation(directory, changes)
    except (OSError, ValueError, PermissionError) as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
