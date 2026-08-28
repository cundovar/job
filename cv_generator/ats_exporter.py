from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, Dict, Iterable
from urllib.parse import urlparse


def _payload(final_cv: Dict[str, Any]) -> Dict[str, Any]:
    cv = final_cv.get("cv")
    return cv if isinstance(cv, dict) else final_cv


def _education_text(education: Dict[str, Any]) -> str:
    return " — ".join(
        str(value)
        for value in (
            education.get("year"),
            education.get("title"),
            education.get("level"),
            education.get("status") or education.get("school"),
        )
        if value
    )


def _display_url(value: Any) -> str:
    raw = str(value or "").strip()
    parsed = urlparse(raw)
    label = f"{parsed.netloc}{parsed.path}" if parsed.netloc else raw
    return label.removeprefix("www.").rstrip("/")


def cv_to_ats_html(final_cv: Dict[str, Any], candidate_name: str = "Facundo Varas") -> str:
    cv = _payload(final_cv)
    contact = cv.get("contact", {})
    contact_values = [contact.get("email"), contact.get("phone"), cv.get("location"), contact.get("portfolio"), contact.get("github")]
    parts = [
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>CV ATS — {escape(candidate_name)}</title>",
        "<style>body{max-width:760px;margin:32px auto;padding:0 24px;font:15px/1.45 Arial,sans-serif;color:#111}",
        "h1{font-size:26px;margin:0}h2{font-size:17px;margin:24px 0 8px;border-bottom:1px solid #555}",
        "h3{font-size:15px;margin:16px 0 4px}p{margin:4px 0}ul{margin:6px 0 10px;padding-left:22px}</style></head><body><main>",
        f"<h1>{escape(candidate_name)}</h1>",
        f"<p><strong>{escape(str(cv.get('title') or ''))}</strong></p>",
        f"<p>{escape(' | '.join(str(item) for item in contact_values if item))}</p>",
        "<h2>Profil</h2>",
        f"<p>{escape(str(cv.get('profile') or ''))}</p>",
        "<h2>Compétences</h2>",
    ]
    for section in cv.get("skills", []):
        parts.append(
            f"<p><strong>{escape(str(section.get('title') or ''))} :</strong> "
            f"{escape(', '.join(str(item) for item in section.get('items', [])))}</p>"
        )
    parts.append("<h2>Expériences professionnelles</h2>")
    for experience in cv.get("experiences", []):
        parts.extend(
            [
                f"<h3>{escape(str(experience.get('title') or ''))} — {escape(str(experience.get('organization') or ''))}</h3>",
                f"<p>{escape(str(experience.get('period') or ''))}</p>",
                "<ul>",
                *(f"<li>{escape(str(item))}</li>" for item in experience.get("bullets", [])),
                "</ul>",
            ]
        )
        for link in experience.get("links", [])[:1]:
            parts.append(f"<p><a href='{escape(str(link), quote=True)}'>{escape(_display_url(link))}</a></p>")
    if cv.get("projects"):
        parts.append("<h2>Projets</h2>")
        for project in cv.get("projects", []):
            parts.append(
                f"<p><strong>{escape(str(project.get('title') or ''))}</strong> — "
                f"{escape(str(project.get('description') or ''))}</p>"
            )
            for link in project.get("links", [])[:1]:
                parts.append(f"<p><a href='{escape(str(link), quote=True)}'>{escape(_display_url(link))}</a></p>")
    if cv.get("education"):
        parts.append("<h2>Formation</h2>")
        parts.extend(f"<p>{escape(_education_text(item))}</p>" for item in cv.get("education", []))
    if cv.get("languages"):
        parts.append("<h2>Langues</h2>")
        parts.extend(
            f"<p>{escape(str(item.get('name') or ''))} — {escape(str(item.get('level') or ''))}</p>"
            for item in cv.get("languages", [])
        )
    parts.append("</main></body></html>")
    return "".join(parts)


def _paragraphs(values: Iterable[str], style: Any) -> list[Any]:
    from reportlab.platypus import Paragraph, Spacer

    blocks = []
    for value in values:
        if not value:
            continue
        blocks.extend([Paragraph(escape(str(value)), style), Spacer(1, 2)])
    return blocks


def cv_to_ats_pdf(
    final_cv: Dict[str, Any],
    output_path: str | Path,
    candidate_name: str = "Facundo Varas",
) -> None:
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

    cv = _payload(final_cv)
    contact = cv.get("contact", {})
    styles = getSampleStyleSheet()
    title = ParagraphStyle("AtsTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=17, leading=20, alignment=TA_LEFT, spaceAfter=3)
    target = ParagraphStyle("AtsTarget", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10.5, leading=12, spaceAfter=3)
    heading = ParagraphStyle("AtsHeading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=13, spaceBefore=7, spaceAfter=3)
    body = ParagraphStyle("AtsBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=9, leading=11, spaceAfter=2)
    meta = ParagraphStyle("AtsMeta", parent=body, fontName="Helvetica-Oblique", fontSize=8.5, leading=10)
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=13 * mm,
        bottomMargin=13 * mm,
        title=f"CV ATS - {candidate_name}",
        author=candidate_name,
    )
    story: list[Any] = [Paragraph(escape(candidate_name), title), Paragraph(escape(str(cv.get("title") or "")), target)]
    contact_values = [contact.get("email"), contact.get("phone"), cv.get("location"), contact.get("portfolio"), contact.get("github")]
    story.extend(_paragraphs([" | ".join(str(item) for item in contact_values if item)], body))
    story.extend([Paragraph("Profil", heading), Paragraph(escape(str(cv.get("profile") or "")), body)])
    story.append(Paragraph("Compétences", heading))
    for section in cv.get("skills", []):
        value = f"<b>{escape(str(section.get('title') or ''))} :</b> {escape(', '.join(str(item) for item in section.get('items', [])))}"
        story.append(Paragraph(value, body))
    story.append(Paragraph("Expériences professionnelles", heading))
    for experience in cv.get("experiences", []):
        story.append(
            Paragraph(
                f"<b>{escape(str(experience.get('title') or ''))}</b> — {escape(str(experience.get('organization') or ''))}",
                body,
            )
        )
        story.append(Paragraph(escape(str(experience.get("period") or "")), meta))
        story.extend(_paragraphs((_display_url(link) for link in experience.get("links", [])[:1]), meta))
        bullets = [ListItem(Paragraph(escape(str(item)), body)) for item in experience.get("bullets", [])]
        if bullets:
            story.append(ListFlowable(bullets, bulletType="bullet", leftIndent=14, bulletFontName="Helvetica"))
        story.append(Spacer(1, 3))
    if cv.get("projects"):
        story.append(Paragraph("Projets", heading))
        for project in cv.get("projects", []):
            story.append(
                Paragraph(
                    f"<b>{escape(str(project.get('title') or ''))}</b> — {escape(str(project.get('description') or ''))}",
                    body,
                )
            )
            story.extend(_paragraphs((_display_url(link) for link in project.get("links", [])[:1]), meta))
    if cv.get("education"):
        story.append(Paragraph("Formation", heading))
        story.extend(_paragraphs((_education_text(item) for item in cv.get("education", [])), body))
    if cv.get("languages"):
        story.append(Paragraph("Langues", heading))
        story.extend(
            _paragraphs(
                (f"{item.get('name', '')} — {item.get('level', '')}" for item in cv.get("languages", [])),
                body,
            )
        )
    document.build(story)
