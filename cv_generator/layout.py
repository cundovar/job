"""Shared layout measurements used by PDF rendering and quality checks."""

from __future__ import annotations

from typing import List

from reportlab.pdfbase.pdfmetrics import stringWidth


IDENTITY_MAIN_WIDTH = 595.276 - 26.0 - 26.0 - 132.0 - 22.0
IDENTITY_TITLE_MAX_WIDTH = IDENTITY_MAIN_WIDTH - 34.0
IDENTITY_TITLE_MIN_SIZE = 8.0
IDENTITY_TITLE_TRACKING = 2.2


def tracked_width(text: str, size: float = IDENTITY_TITLE_MIN_SIZE, tracking: float = IDENTITY_TITLE_TRACKING) -> float:
    value = str(text or "")
    return stringWidth(value, "Helvetica", size) + max(0, len(value) - 1) * tracking


def wrap_tracked_title(
    text: str,
    max_width: float = IDENTITY_TITLE_MAX_WIDTH,
    size: float = IDENTITY_TITLE_MIN_SIZE,
    tracking: float = IDENTITY_TITLE_TRACKING,
) -> List[str]:
    words = str(text or "").upper().split()
    if not words:
        return [""]
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or tracked_width(candidate, size, tracking) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def title_requires_wrap(text: str) -> bool:
    return tracked_width(str(text or "").upper()) > IDENTITY_TITLE_MAX_WIDTH
