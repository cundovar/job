"""Régénère la lettre et le mail d'un dossier existant avec de nouvelles consignes.

Entrée stdin : {"id": "<dossier>", "consignes": "...", "mail_note": "..."}.
Sortie stdout : JSON {"ok": true, "id": ..., "consignes": {...}}.
Le serveur Node vérifie avant l'appel qu'aucune tentative d'envoi n'existe.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from applications import rebuild_candidatures_index
from applications.application_builder import regenerate_letter_and_email
from pipeline import load_criteria

PROJECT = Path(__file__).resolve().parents[1]
APPLICATIONS_DIR = PROJECT / "output" / "applications"


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Payload JSON invalide: {exc}")
    if not isinstance(payload, dict):
        raise SystemExit("Payload attendu: {\"id\": ..., \"consignes\": ..., \"mail_note\": ...}")

    directory = (APPLICATIONS_DIR / str(payload.get("id") or "")).resolve()
    if directory.parent != APPLICATIONS_DIR.resolve() or not directory.is_dir():
        raise SystemExit(f"Dossier candidature introuvable : {payload.get('id')}")

    criteria = load_criteria()
    result = regenerate_letter_and_email(
        directory,
        consignes=str(payload.get("consignes") or ""),
        mail_note=str(payload.get("mail_note") or ""),
        user_profile=criteria.get("user_profile", {}),
    )
    index_result = rebuild_candidatures_index(
        APPLICATIONS_DIR,
        PROJECT / "front" / "public" / "data" / "candidatures.json",
    )
    print(json.dumps({"ok": True, **result, "index": index_result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
