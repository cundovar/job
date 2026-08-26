"""
CV variant loading — reads data/cv_master_profile.json (single source of truth).

Replaces the former config/cv_profiles.yaml, which pointed at PDF files that
only ever existed on Cundo's laptop. Variants here are the ones cv_generator
actually builds from.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

DEFAULT_MASTER_PATH = "data/cv_master_profile.json"


@dataclass(frozen=True)
class CVVariant:
    id: str
    name: str
    tags: List[str] = field(default_factory=list)
    profile: str = ""


def _master_path(path: str | None = None) -> str:
    return path or os.getenv("CV_MASTER_PROFILE", DEFAULT_MASTER_PATH)


def load_master_profile(path: str | None = None) -> Dict[str, Any]:
    with open(_master_path(path), "r", encoding="utf-8") as f:
        return json.load(f) or {}


def load_cv_variants(path: str | None = None) -> List[CVVariant]:
    master = load_master_profile(path)
    title_variants = master.get("positioning", {}).get("title_variants", {})

    variants = []
    for item in master.get("cv_variants", []):
        variant_id = item.get("id")
        if not variant_id:
            continue
        variants.append(
            CVVariant(
                id=variant_id,
                name=title_variants.get(variant_id) or item.get("title") or variant_id,
                tags=list(item.get("tags", [])),
                profile=item.get("profile", ""),
            )
        )
    return variants


def default_priority(path: str | None = None) -> List[str]:
    master = load_master_profile(path)
    return list(master.get("positioning", {}).get("default_priority", []))
