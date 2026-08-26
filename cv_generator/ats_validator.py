from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from pypdf import PdfReader

from .utils import normalize


def extract_pdf_text(path: str | Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _payload(final_cv: Dict[str, Any]) -> Dict[str, Any]:
    cv = final_cv.get("cv")
    return cv if isinstance(cv, dict) else final_cv


def _expected_fields(final_cv: Dict[str, Any], candidate_name: str) -> List[Dict[str, str]]:
    cv = _payload(final_cv)
    contact = cv.get("contact", {})
    fields: List[Dict[str, str]] = [
        {"id": "candidate_name", "value": candidate_name},
        {"id": "target_title", "value": str(cv.get("title") or "")},
        {"id": "email", "value": str(contact.get("email") or "")},
    ]
    for index, experience in enumerate(cv.get("experiences", [])):
        fields.extend(
            [
                {"id": f"experience_{index}_title", "value": str(experience.get("title") or "")},
                {"id": f"experience_{index}_organization", "value": str(experience.get("organization") or "")},
                {"id": f"experience_{index}_period", "value": str(experience.get("period") or "")},
            ]
        )
    for index, education in enumerate(cv.get("education", [])):
        fields.append({"id": f"education_{index}_title", "value": str(education.get("title") or "")})
    return [item for item in fields if item["value"].strip()]


def validate_ats_pdf(
    path: str | Path,
    final_cv: Dict[str, Any],
    candidate_name: str = "Facundo Varas",
) -> Dict[str, Any]:
    raw_text = extract_pdf_text(path)
    text = normalize(raw_text)
    expected = _expected_fields(final_cv, candidate_name)
    found = [item["id"] for item in expected if normalize(item["value"]) in text]
    missing = [item["id"] for item in expected if item["id"] not in found]
    return {
        "status": "pass" if not missing else "fail",
        "reason": "Tous les champs essentiels sont extractibles." if not missing else "Certains champs essentiels ne sont pas extractibles.",
        "found": found,
        "missing": missing,
        "page_count": len(PdfReader(str(path)).pages),
        "extracted_characters": len(raw_text),
    }
