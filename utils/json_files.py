"""Lecture et écriture des fichiers JSON du projet.

L'écriture passe par un fichier temporaire puis un renommage : un fichier lu
pendant une écriture (le serveur Node et les scripts Python partagent
``data/applications_tracker.json``) est soit l'ancien, soit le nouveau, jamais
un JSON coupé en deux.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_json_atomic(path: str | Path, data: Any, *, indent: int = 2) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=indent)
        if target.exists():
            # mkstemp crée en 0600 : on garde les droits du fichier remplacé.
            os.chmod(temporary, target.stat().st_mode & 0o777)
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
