"""Aperçu du mail HTML d'un dossier : ``python -m applications.mail_preview <dossier>``.

Rend exactement ce que ``send.py`` enverrait (même découpage objet/corps,
même fonction ``dossier_mail_html``, même adresse d'expéditeur), sans
toucher au fournisseur d'envoi. Sortie : JSON {ok, subject, html}.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .mail_template import dossier_mail_html
from .send import _mail_parts
from .sender import _load_repo_env


def sender_address() -> str:
    """L'adresse que l'expéditeur réel utiliserait (Brevo d'abord, puis SMTP)."""
    _load_repo_env()
    if os.getenv("BREVO_API_KEY", "").strip():
        return os.getenv("BREVO_SENDER_EMAIL") or os.getenv("EMAIL_SENDER") or ""
    return os.getenv("EMAIL_SENDER") or ""


def preview(directory: str | Path) -> dict:
    directory = Path(directory)
    mail_path = directory / "mail_candidature.md"
    if not mail_path.is_file():
        raise FileNotFoundError(f"Aucun mail dans {directory.name}")
    subject, body = _mail_parts(mail_path)
    html = dossier_mail_html(directory, subject, body, sender_email=sender_address())
    return {"ok": True, "subject": subject, "html": html}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("Usage : python -m applications.mail_preview <dossier>", file=sys.stderr)
        return 2
    try:
        result = preview(args[0])
    except (OSError, ValueError) as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
