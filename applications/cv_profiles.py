"""
CV profile configuration loading.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml


@dataclass(frozen=True)
class CVProfile:
    id: str
    name: str
    path: str
    best_for: List[str]
    alternatives: List[str] = field(default_factory=list)

    @property
    def existing_paths(self) -> List[str]:
        paths = [self.path, *self.alternatives]
        return [path for path in paths if Path(path).exists()]


def load_cv_profiles(path: str = "config/cv_profiles.yaml") -> List[CVProfile]:
    with open(path, "r", encoding="utf-8") as f:
        config: Dict[str, Any] = yaml.safe_load(f) or {}

    profiles = []
    for item in config.get("cvs", []):
        profiles.append(
            CVProfile(
                id=item["id"],
                name=item["name"],
                path=item["path"],
                alternatives=item.get("alternatives", []),
                best_for=item.get("best_for", []),
            )
        )

    return profiles
