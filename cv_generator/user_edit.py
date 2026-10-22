"""Version du CV modifiée par le candidat.

Le candidat a la main sur son CV (demande Cundo, 22/10/2026). Après une
génération, il peut tout réécrire : titre, accroche, expériences (y compris en
ajouter), puces, projets, compétences, formation, rubrique « Réalisations en
ligne ». Comme un PDF qu'il ajoute lui-même (``cv_upload.pdf``), sa version
remplace le CV généré à l'envoi : c'est sa parole, pas une affirmation de l'IA,
donc le contrôle de véracité ne la juge pas.

Ce module ne fait aucun appel IA. Il :
- nettoie la structure reçue (champs connus, longueurs bornées, liens http(s),
  aucun lien retiré par ``rules.RETIRED_LINK_HOSTS``) ;
- prend les coordonnées revues par le candidat (email, téléphone, liens vérifiés),
  sinon celles produites pour la variante ;
- refait les deux PDF (design et ATS) ;
- signale, sans rien bloquer, les contraintes de mise en page dépassées.

Fichiers, dans ``<dossier>/cv/`` : ``cv_edit.json``, ``cv_edit.pdf``,
``cv_edit_ats.pdf``. Le CV généré (``cv_content.json`` et les autres) reste
intact : retirer la version modifiée le rend de nouveau effectif.

CLI : ``python -m cv_generator.user_edit <dossier> --input <fichier.json>``
      ``python -m cv_generator.user_edit <dossier> --reset``
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from . import rules
from .utils import load_json

EDIT_JSON = "cv_edit.json"
EDIT_PDF = "cv_edit.pdf"
EDIT_ATS_PDF = "cv_edit_ats.pdf"
EDIT_FILES = (EDIT_JSON, EDIT_PDF, EDIT_ATS_PDF)

SECTIONS = ("profile", "skills", "experiences", "projects", "education")


class UserEditError(ValueError):
    """Une version modifiée inutilisable : le message dit quoi corriger."""


def _text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _texts(values: Any, limit: int, count: int) -> List[str]:
    if not isinstance(values, list):
        return []
    items = [_text(value, limit) for value in values]
    return [item for item in items if item][:count]


def _links(values: Any, count: int = 3) -> List[str]:
    if not isinstance(values, list):
        return []
    links = [_text(value, 300) for value in values]
    links = [link for link in links if link.startswith(("https://", "http://"))]
    return rules.shown_links(links)[:count]


def _experience(raw: Any) -> Dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    entry = {
        "id": _text(raw.get("id"), 80),
        "organization": _text(raw.get("organization"), 200),
        "title": _text(raw.get("title"), 200),
        "period": _text(raw.get("period"), 60),
        "bullets": _texts(raw.get("bullets"), 400, 8),
        "links": _links(raw.get("links"), 2),
    }
    if not (entry["organization"] or entry["title"] or entry["bullets"]):
        return None
    return entry


def _project(raw: Any) -> Dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    entry = {
        "id": _text(raw.get("id"), 80),
        "title": _text(raw.get("title"), 200),
        "year": _text(raw.get("year"), 20),
        "description": _text(raw.get("description"), 1200),
        "technologies": _texts(raw.get("technologies"), 60, 20),
        "links": _links(raw.get("links"), 2),
    }
    if not (entry["title"] or entry["description"]):
        return None
    return entry


def _skill_group(raw: Any) -> Dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    items = _texts(raw.get("items"), 80, 25)
    if not items:
        return None
    return {"title": _text(raw.get("title"), 60) or "Compétences", "items": items}


def _education(raw: Any) -> Dict[str, Any] | None:
    if isinstance(raw, str):
        raw = {"title": raw}
    if not isinstance(raw, dict):
        return None
    entry = {key: _text(raw.get(key), 200) for key in ("year", "title", "level", "school", "status")}
    entry = {key: value for key, value in entry.items() if value}
    return entry if entry.get("title") else None


def _language(raw: Any) -> Dict[str, str] | None:
    """Une langue sous la forme que les exports savent rendre : {name, level}."""
    if isinstance(raw, str):
        raw = {"name": raw}
    if not isinstance(raw, dict):
        return None
    name = _text(raw.get("name"), 80)
    if not name:
        return None
    level = _text(raw.get("level"), 80)
    return {"name": name, "level": level} if level else {"name": name}


def _online_work(raw: Any) -> List[Dict[str, str]] | None:
    if raw is None:
        return None
    if not isinstance(raw, list):
        return []
    items = []
    for entry in raw[:6]:
        if not isinstance(entry, dict):
            continue
        url = _links([entry.get("url")], 1)
        if url:
            items.append({"label": _text(entry.get("label"), 80) or url[0], "url": url[0]})
    return items


_EMAIL = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_PHONE = re.compile(r"^[0-9+().\s-]{6,30}$")
CONTACT_LINK_KEYS = ("portfolio", "github", "linkedin")


def _contact(raw: Any, generated: Dict[str, Any]) -> Dict[str, str]:
    """Coordonnées revues par le candidat ; sans saisie, celles de la génération.

    Un champ vidé disparaît du CV. Une valeur invalide (email, téléphone, lien
    non http) est refusée en le disant : elle partirait telle quelle chez un
    recruteur.
    """
    if not isinstance(raw, dict):
        return dict(generated or {})
    contact: Dict[str, str] = {}
    email = _text(raw.get("email"), 120)
    if email:
        if not _EMAIL.match(email):
            raise UserEditError(f"Adresse email invalide : « {email} ».")
        contact["email"] = email
    phone = _text(raw.get("phone"), 30)
    if phone:
        if not _PHONE.match(phone):
            raise UserEditError(f"Numéro de téléphone invalide : « {phone} ».")
        contact["phone"] = phone
    for key in CONTACT_LINK_KEYS:
        value = _text(raw.get(key), 300)
        if not value:
            continue
        links = _links([value], 1)
        if not links:
            raise UserEditError(f"Lien « {key} » invalide : il doit commencer par https:// et ne pas être retiré.")
        contact[key] = links[0]
    return contact


def _clean(items: Any, cleaner, count: int) -> List[Any]:
    if not isinstance(items, list):
        return []
    cleaned = [cleaner(item) for item in items[: count * 2]]
    return [item for item in cleaned if item][:count]


def sanitize_cv(edited: Any, generated_cv: Dict[str, Any]) -> Dict[str, Any]:
    """La version du candidat, réduite aux champs que les exports savent rendre."""
    if not isinstance(edited, dict):
        raise UserEditError("La version modifiée doit être un objet CV.")
    cv: Dict[str, Any] = {
        "title": _text(edited.get("title"), 200),
        "profile": _text(edited.get("profile"), 1200),
        "section_order": [
            section for section in edited.get("section_order") or generated_cv.get("section_order") or SECTIONS
            if section in SECTIONS
        ] or list(SECTIONS),
        # Coordonnées : celles que le candidat a revues (demande Cundo
        # 22/10/2026), sinon celles produites pour la variante.
        "contact": _contact(edited.get("contact"), generated_cv.get("contact", {})),
        "location": (
            _text(edited.get("location"), 80)
            if "location" in edited
            else generated_cv.get("location", "")
        ),
        "skills": _clean(edited.get("skills"), _skill_group, 8),
        "experiences": _clean(edited.get("experiences"), _experience, 12),
        "projects": _clean(edited.get("projects"), _project, 6),
        "education": _clean(edited.get("education"), _education, 8),
        "languages": _clean(edited.get("languages"), _language, 8),
    }
    online = _online_work(edited.get("online_work"))
    if online is not None:
        cv["online_work"] = online
    if isinstance(edited.get("show_online_work"), bool):
        cv["show_online_work"] = edited["show_online_work"]
    if not cv["title"]:
        raise UserEditError("Le titre du CV est vide.")
    if not cv["experiences"]:
        raise UserEditError("Le CV doit garder au moins une expérience.")
    return cv


def layout_warnings(cv: Dict[str, Any], master: Dict[str, Any]) -> List[str]:
    """Contraintes de mise en page dépassées : signalées, jamais bloquantes."""
    layout = master.get("layout_constraints", {}) or {}
    warnings: List[str] = []
    max_profile = int(layout.get("max_profile_chars", 240))
    if len(cv.get("profile", "")) > max_profile:
        warnings.append(f"Accroche de {len(cv['profile'])} caractères (repère : {max_profile}).")
    max_bullet = int(layout.get("max_bullet_chars", 145))
    for exp in cv.get("experiences", []):
        for bullet in exp.get("bullets", []):
            if len(bullet) > max_bullet:
                warnings.append(
                    f"Puce de {len(bullet)} caractères dans « {exp.get('title') or exp.get('organization')} » "
                    f"(repère : {max_bullet})."
                )
    max_experiences = int(layout.get("max_experiences", 4))
    by_variant = layout.get("max_experiences_by_variant") or {}
    if by_variant:
        max_experiences = max([max_experiences, *[int(v) for v in by_variant.values() if isinstance(v, int)]])
    if len(cv.get("experiences", [])) > max_experiences:
        warnings.append(
            f"{len(cv['experiences'])} expériences : le CV risque de dépasser une page."
        )
    return warnings


def generated_content(cv_dir: Path) -> Dict[str, Any]:
    path = cv_dir / "cv_content.json"
    if not path.is_file():
        raise UserEditError("Aucun CV généré dans ce dossier : génère-le avant de le modifier.")
    return load_json(path)


def current_content(cv_dir: Path) -> Dict[str, Any]:
    """La version à afficher dans l'éditeur : la tienne si elle existe."""
    edit = cv_dir / EDIT_JSON
    if edit.is_file():
        return load_json(edit)
    return generated_content(cv_dir)


def save_user_edit(dossier: Path, edited_cv: Any, master: Dict[str, Any]) -> Dict[str, Any]:
    from .ats_exporter import cv_to_ats_pdf
    from .exporters import cv_to_pdf

    cv_dir = dossier / "cv"
    generated = generated_content(cv_dir)
    cv = sanitize_cv(edited_cv, generated.get("cv", {}) or {})
    content = {
        "agent": "edition_candidat",
        "base_variant": generated.get("base_variant"),
        "generated_for": generated.get("generated_for", {}),
        "edited_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cv": cv,
        "warnings": layout_warnings(cv, master),
    }
    # PDF d'abord, dans des fichiers temporaires : une version qui ne se rend
    # pas ne remplace pas celle qui marchait.
    tmp_pdf = cv_dir / f"{EDIT_PDF}.tmp"
    tmp_ats = cv_dir / f"{EDIT_ATS_PDF}.tmp"
    try:
        cv_to_pdf(content, tmp_pdf)
        cv_to_ats_pdf(content, tmp_ats)
    except Exception as exc:
        for path in (tmp_pdf, tmp_ats):
            path.unlink(missing_ok=True)
        raise UserEditError(f"Le PDF n'a pas pu être produit : {exc}") from exc
    tmp_json = cv_dir / f"{EDIT_JSON}.tmp"
    tmp_json.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_pdf.replace(cv_dir / EDIT_PDF)
    tmp_ats.replace(cv_dir / EDIT_ATS_PDF)
    tmp_json.replace(cv_dir / EDIT_JSON)
    return content


def reset_user_edit(dossier: Path) -> List[str]:
    removed = []
    for name in EDIT_FILES:
        path = dossier / "cv" / name
        if path.exists():
            path.unlink()
            removed.append(name)
    return removed


def _master_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "cv_master_profile.json"


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Version du CV modifiée par le candidat.")
    parser.add_argument("dossier", type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", type=Path, help="JSON du CV modifié ({cv: …} ou le CV seul)")
    group.add_argument("--reset", action="store_true", help="Retire la version modifiée")
    group.add_argument("--show", action="store_true", help="Version à éditer, avec les réalisations affichées")
    args = parser.parse_args(argv)
    try:
        if args.show:
            from .cv_pdf_design import _online_work

            cv_dir = args.dossier / "cv"
            content = current_content(cv_dir)
            cv = content.get("cv", {}) or {}
            print(json.dumps({
                "ok": True,
                "edited": (cv_dir / EDIT_JSON).is_file(),
                "edited_at": content.get("edited_at"),
                "warnings": content.get("warnings") or [],
                "cv": cv,
                # Ce que la rubrique affiche réellement, même quand elle est
                # choisie automatiquement : l'éditeur part de là.
                "online_work_effective": [{"label": label, "url": url} for label, url in _online_work(cv)],
            }, ensure_ascii=False))
            return 0
        if args.reset:
            print(json.dumps({"ok": True, "removed": reset_user_edit(args.dossier)}, ensure_ascii=False))
            return 0
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        edited = payload.get("cv", payload) if isinstance(payload, dict) else payload
        master = load_json(_master_path()) if _master_path().is_file() else {}
        content = save_user_edit(args.dossier, edited, master)
        print(json.dumps({"ok": True, "warnings": content["warnings"], "edited_at": content["edited_at"]}, ensure_ascii=False))
        return 0
    except (UserEditError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
