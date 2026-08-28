from __future__ import annotations

import json
import base64
import mimetypes
from html import escape
from pathlib import Path
from typing import Any, Dict, List

from .layout import (
    IDENTITY_TITLE_MAX_WIDTH,
    IDENTITY_TITLE_MIN_SIZE,
    IDENTITY_TITLE_TRACKING,
    wrap_tracked_title,
)


DEFAULT_DESIGN_SYSTEM = "config/cv_design_system.json"
DEFAULT_PORTRAIT = Path(__file__).resolve().parent.parent / "assets" / "cv" / "facundo-varas.jpg"
PDF_PORTRAIT_DIAMETER = 119.0


def _identity_baselines(top: float, portrait_diameter: float = PDF_PORTRAIT_DIAMETER) -> tuple[float, float]:
    """Return name/title baselines for a block visually centered on the portrait."""
    portrait_center = top - portrait_diameter / 2
    return portrait_center + 6.5, portrait_center - 30.5


def _portrait_data_uri(path: str | Path = DEFAULT_PORTRAIT) -> str:
    portrait = Path(path)
    if not portrait.exists():
        return ""
    mime = mimetypes.guess_type(portrait.name)[0] or "image/jpeg"
    encoded = base64.b64encode(portrait.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _load_design_system(path: str | Path = DEFAULT_DESIGN_SYSTEM) -> Dict[str, Any]:
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _style(design: Dict[str, Any], name: str, key: str, default: Any) -> Any:
    return design.get("typography", {}).get("styles", {}).get(name, {}).get(key, default)


def cv_to_markdown(final_cv: Dict[str, Any], canva: bool = False) -> str:
    cv = final_cv.get("cv", {})
    contact = cv.get("contact", {})
    lines: List[str] = []
    lines.append("# Facundo Varas")
    lines.append("")
    lines.append(f"## {cv.get('title', 'CV personnalisé')}")
    lines.append("")
    contact_bits = [cv.get("location"), contact.get("email"), contact.get("phone"), contact.get("portfolio"), contact.get("github")]
    lines.append(" · ".join(str(bit) for bit in contact_bits if bit))
    lines.append("")
    lines.append("## Profil")
    lines.append("")
    lines.append(cv.get("profile", ""))
    lines.append("")
    lines.append("## Compétences")
    lines.append("")
    for section in cv.get("skills", []):
        lines.append(f"### {section.get('title', '')}")
        lines.append(" · ".join(section.get("items", [])))
        lines.append("")
    lines.append("## Expériences")
    lines.append("")
    for exp in cv.get("experiences", []):
        title = exp.get("title", "")
        org = exp.get("organization", "")
        period = exp.get("period", "")
        lines.append(f"### {org} — {title}".strip(" —"))
        if period:
            lines.append(period)
        lines.append("")
        for bullet in exp.get("bullets", []):
            lines.append(f"- {bullet}")
        lines.append("")
    projects = cv.get("projects", [])
    if projects:
        lines.append("## Projet clé")
        lines.append("")
        for project in projects:
            tech = " · ".join(project.get("technologies", []))
            lines.append(f"### {project.get('title', '')}")
            lines.append(project.get("description", ""))
            if tech:
                lines.append(f"Technologies : {tech}")
            lines.append("")
    lines.append("## Formation")
    lines.append("")
    for edu in cv.get("education", []):
        details = " — ".join(str(x) for x in [edu.get("year"), edu.get("title"), edu.get("level"), edu.get("status") or edu.get("school")] if x)
        lines.append(f"- {details}")
    lines.append("")
    if cv.get("languages"):
        lines.append("## Langues")
        lines.append("")
        lines.extend(f"- {lang.get('name')} : {lang.get('level')}" for lang in cv.get("languages", []))
        lines.append("")
    if canva:
        lines.insert(0, "<!-- Version courte copiables par blocs dans Canva -->")
    return "\n".join(lines).strip() + "\n"


def _section(title: str) -> str:
    return f"<h2>{escape(title)}</h2><div class='section-line'></div>"


def cv_to_html(
    final_cv: Dict[str, Any],
    design_system_path: str | Path = DEFAULT_DESIGN_SYSTEM,
    portrait_path: str | Path = DEFAULT_PORTRAIT,
) -> str:
    """Render an A4 HTML preview following the Canva-derived design system."""
    design = _load_design_system(design_system_path)
    cv = final_cv.get("cv", {})
    contact = cv.get("contact", {})
    colors = design.get("colors", {})
    bg = colors.get("background", "#FFFFFF")
    primary = colors.get("text_primary", "#111111")
    secondary = colors.get("text_secondary", "#606665")
    accent = colors.get("accent", "#788481")
    css_font = "Raleway, 'Avenir Next', 'Century Gothic', Arial, sans-serif"

    contact_items = [
        ("✉", contact.get("email")),
        ("☎", contact.get("phone")),
        ("⌂", cv.get("location")),
        ("↗", contact.get("portfolio")),
        ("⌁", contact.get("github")),
    ]

    portrait_uri = _portrait_data_uri(portrait_path)
    portrait = (
        f"<img class='portrait' src='{portrait_uri}' alt='Portrait de Facundo Varas'>"
        if portrait_uri
        else "<div class='portrait portrait-fallback'>FV</div>"
    )
    sidebar = [portrait, _section("Profil"), f"<p>{escape(cv.get('profile', ''))}</p>"]
    sidebar.append(_section("Contact"))
    for icon, text in contact_items:
        if text:
            sidebar.append(f"<div class='contact-item'><span>{escape(icon)}</span><p>{escape(str(text))}</p></div>")
    if cv.get("languages"):
        sidebar.append(_section("Langues"))
        for lang in cv.get("languages", []):
            sidebar.append(f"<p><strong>{escape(str(lang.get('name', '')))}</strong> — {escape(str(lang.get('level', '')))}</p>")

    main = [
        "<header>",
        "<h1>Facundo Varas</h1>",
        f"<div class='target-title'>{escape(cv.get('title', 'CV personnalisé'))}</div>",
        "</header>",
        _section("Compétences"),
    ]
    for section in cv.get("skills", []):
        main.append(
            f"<p class='skill'><strong>{escape(section.get('title', ''))}</strong>: "
            f"{escape(', '.join(section.get('items', [])))}</p>"
        )
    main.append(_section("Expériences"))
    for exp in cv.get("experiences", [])[:4]:
        bullets = "".join(f"<li>{escape(str(b))}</li>" for b in exp.get("bullets", [])[:4])
        main.append(
            "<article class='experience'>"
            f"<div class='meta'><strong>{escape(str(exp.get('period', '')))}</strong><br>{escape(str(exp.get('organization', '')))}</div>"
            "<div class='desc'>"
            f"<h3>{escape(str(exp.get('title', '')))}</h3>"
            f"<ul>{bullets}</ul>"
            "</div></article>"
        )
    projects = cv.get("projects", [])
    if projects:
        main.append(_section("Projets personnels"))
        for project in projects[:2]:
            tech = ", ".join(project.get("technologies", []))
            main.append(
                f"<p class='project'><strong>{escape(str(project.get('title', '')))}</strong> — "
                f"{escape(str(project.get('description', '')))}"
                f" <span>{escape(tech)}</span></p>"
            )
    if cv.get("education"):
        main.append(_section("Formation"))
        for edu in cv.get("education", [])[:2]:
            details = " — ".join(
                str(x)
                for x in [edu.get("year"), edu.get("title"), edu.get("level"), edu.get("status") or edu.get("school")]
                if x
            )
            main.append(f"<p class='education'><strong>{escape(details)}</strong></p>")

    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CV personnalisé - Facundo Varas</title>
<style>
  @page {{ size: A4; margin: 0; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #ececec; color: {primary}; font-family: {css_font}; }}
  .page {{ width: 794px; min-height: 1123px; margin: 0 auto; background: {bg}; padding: 34px 35px 30px; display: grid; grid-template-columns: 24% 6% 70%; }}
  aside {{ grid-column: 1; padding-top: 4px; color: {secondary}; }}
  main {{ grid-column: 3; }}
  header {{ height: 128px; display: flex; flex-direction: column; justify-content: center; }}
  h1 {{ margin: 0 0 8px; font-size: 25pt; font-weight: 400; letter-spacing: .01em; line-height: 1.1; }}
  .target-title, h2 {{ text-transform: uppercase; letter-spacing: .32em; font-weight: 400; color: {primary}; }}
  .target-title {{ font-size: 9pt; line-height: 1.35; max-width: calc(100% - 34px); overflow-wrap: anywhere; }}
  h2 {{ margin: 24px 0 0; font-size: 8.3pt; line-height: 1.2; }}
  .section-line {{ width: 31px; height: 3px; background: {accent}; margin: 8px 0 12px; }}
  p, li {{ font-size: 7.6pt; line-height: 1.48; margin: 0 0 8px; }}
  .portrait {{ width: 112px; height: 112px; border-radius: 50%; object-fit: cover; object-position: center; background: #d9dddc; display:block; margin: 2px 0 58px; filter: grayscale(1); }}
  .portrait-fallback {{ color: {primary}; display:flex; align-items:center; justify-content:center; font-size: 18px; }}
  .contact-item {{ display: grid; grid-template-columns: 9px 1fr; gap: 5px; align-items: start; margin-bottom: 6px; }}
  .contact-item span {{ font-size: 7px; color: {accent}; }}
  .contact-item p {{ font-size: 6.7pt; line-height: 1.4; overflow-wrap: anywhere; }}
  .skill strong {{ font-weight: 700; }}
  .experience {{ display: grid; grid-template-columns: 20% 80%; gap: 14px; margin-bottom: 20px; }}
  .meta, .meta strong {{ color: {secondary}; font-size: 6.5pt; line-height: 1.3; font-weight: 600; }}
  h3 {{ margin: 0 0 7px; font-size: 8pt; line-height: 1.25; font-weight: 700; text-transform: uppercase; letter-spacing: .01em; }}
  ul {{ margin: 0 0 0 9px; padding: 0; }}
  li {{ padding-left: 0; margin-bottom: 4px; }}
  .project span {{ color: {secondary}; }}
  @media (max-width: 820px) {{ .page {{ width: 100%; min-height: auto; grid-template-columns: 1fr; padding: 24px; }} aside, main {{ grid-column: 1; }} header {{ height: auto; margin-bottom: 20px; justify-content: flex-start; }} }}
</style>
</head>
<body>
<div class="page">
  <aside>{''.join(sidebar)}</aside>
  <main>{''.join(main)}</main>
</div>
</body>
</html>
"""


def cv_to_pdf(
    final_cv: Dict[str, Any],
    output_path: str | Path,
    design_system_path: str | Path = DEFAULT_DESIGN_SYSTEM,
    portrait_path: str | Path = DEFAULT_PORTRAIT,
) -> None:
    """Create a polished, one-page CV inspired by the Canva reference.

    Every block is measured before the next block starts. Font sizes are
    reduced in small steps only when the main column would otherwise overflow.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    design = _load_design_system(design_system_path)
    cv = final_cv.get("cv", {})
    contact = cv.get("contact", {})
    colors_cfg = design.get("colors", {})
    primary = colors.HexColor(colors_cfg.get("text_primary", "#111111"))
    secondary = colors.HexColor(colors_cfg.get("text_secondary", "#606665"))
    accent = colors.HexColor(colors_cfg.get("accent", "#788481"))
    muted = colors.HexColor("#D9DDDC")

    regular_font = "Helvetica"
    bold_font = "Helvetica-Bold"
    font_dir = Path("/usr/share/fonts/truetype/dejavu")
    try:
        pdfmetrics.registerFont(TTFont("CVSans", str(font_dir / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("CVSans-Bold", str(font_dir / "DejaVuSans-Bold.ttf")))
        regular_font, bold_font = "CVSans", "CVSans-Bold"
    except Exception:
        pass

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out), pagesize=A4)
    width, height = A4
    left, right, top, bottom = 26.0, width - 26.0, height - 30.0, 27.0
    sidebar_x, sidebar_w, gutter = left, 132.0, 22.0
    main_x = sidebar_x + sidebar_w + gutter
    main_w = right - main_x
    sidebar_inner_w = sidebar_w - 4.0

    def set_font(size: float, bold: bool = False, color=primary) -> None:
        c.setFillColor(color)
        c.setFont(bold_font if bold else regular_font, size)

    def wrap(text: str, max_w: float, size: float, bold: bool = False) -> List[str]:
        font = bold_font if bold else regular_font
        words = str(text or "").replace("\u202f", " ").split()
        lines: List[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if not current or stringWidth(candidate, font, size) <= max_w:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    def text_height(text: str, max_w: float, size: float, leading: float, bold: bool = False) -> float:
        return len(wrap(text, max_w, size, bold)) * leading

    def draw_wrapped(
        text: str,
        x: float,
        y: float,
        max_w: float,
        size: float,
        leading: float,
        bold: bool = False,
        color=primary,
        bullet: bool = False,
    ) -> float:
        bullet_indent = 9.0 if bullet else 0.0
        set_font(size, bold, color)
        lines = wrap(text, max_w - bullet_indent, size, bold)
        for index, line in enumerate(lines):
            if bullet and index == 0:
                c.setFillColor(accent)
                c.circle(x + 1.7, y + size * 0.35, 1.25, stroke=0, fill=1)
                set_font(size, bold, color)
            c.drawString(x + bullet_indent, y, line)
            y -= leading
        return y

    def draw_tracked(text: str, x: float, y: float, size: float, tracking: float, color=primary) -> None:
        c.saveState()
        tx = c.beginText(x, y)
        tx.setFont(regular_font, size)
        tx.setFillColor(color)
        tx.setCharSpace(tracking)
        tx.textLine(str(text).upper())
        c.drawText(tx)
        c.restoreState()

    def draw_section(title: str, x: float, y: float, scale: float = 1.0) -> float:
        draw_tracked(title, x, y, 10.6 * scale, 3.1 * scale, secondary)
        line_y = y - 15.0 * scale
        c.setFillColor(accent)
        c.rect(x, line_y, 55.0 * scale, 4.5 * scale, stroke=0, fill=1)
        return line_y - 21.0 * scale

    def draw_portrait() -> None:
        portrait = Path(portrait_path)
        diameter = PDF_PORTRAIT_DIAMETER
        x, y = sidebar_x + 9.0, top - diameter
        c.setFillColor(muted)
        c.circle(x + diameter / 2, y + diameter / 2, diameter / 2, stroke=0, fill=1)
        if not portrait.exists():
            set_font(19, False, primary)
            c.drawCentredString(x + diameter / 2, y + diameter / 2 - 6, "FV")
            return
        image = ImageReader(str(portrait))
        iw, ih = image.getSize()
        factor = max(diameter / iw, diameter / ih)
        draw_w, draw_h = iw * factor, ih * factor
        c.saveState()
        clip = c.beginPath()
        clip.circle(x + diameter / 2, y + diameter / 2, diameter / 2)
        c.clipPath(clip, stroke=0, fill=0)
        c.drawImage(
            image,
            x - (draw_w - diameter) / 2,
            y - (draw_h - diameter) / 2,
            width=draw_w,
            height=draw_h,
            mask="auto",
        )
        c.restoreState()

    # The main column controls the adaptive scale. This calculation mirrors
    # the drawing code and fixes the old overlap caused by ignoring metadata.
    meta_w = 82.0
    desc_x = main_x + meta_w + 10.0
    desc_w = main_w - meta_w - 10.0

    def main_bottom(scale: float) -> float:
        body_size, leading = 7.7 * scale, 11.4 * scale
        meta_size, meta_leading = 7.0 * scale, 10.0 * scale
        title_size, title_leading = 8.0 * scale, 10.4 * scale
        y = top - 137.0
        y -= 36.0 * scale
        for skill in cv.get("skills", []):
            text = f"{skill.get('title', '')}: {', '.join(skill.get('items', []))}"
            y -= text_height(text, main_w, body_size, leading)
            y -= 6.5 * scale
        y -= 22.0 * scale + 36.0 * scale
        for exp in cv.get("experiences", [])[:4]:
            meta_h = text_height(exp.get("period", ""), meta_w, meta_size, meta_leading, True)
            meta_h += 3.0 * scale + text_height(exp.get("organization", ""), meta_w, meta_size, meta_leading)
            desc_h = text_height(str(exp.get("title", "")).upper(), desc_w, title_size, title_leading, True)
            desc_h += 4.0 * scale
            for bullet in exp.get("bullets", [])[:3]:
                desc_h += text_height(bullet, desc_w - 9.0, body_size, leading)
                desc_h += 2.5 * scale
            y -= max(meta_h, desc_h) + 17.0 * scale
        if cv.get("projects"):
            y -= 36.0 * scale
            project = cv["projects"][0]
            y -= text_height(project.get("title", ""), main_w, title_size, title_leading, True)
            project_text = f"{project.get('description', '')} - {', '.join(project.get('technologies', []))}"
            y -= 4.0 * scale + text_height(project_text, main_w, body_size, leading)
        if cv.get("education"):
            y -= 22.0 * scale + 36.0 * scale
            for edu in cv.get("education", [])[:2]:
                details = " - ".join(
                    str(value)
                    for value in [edu.get("year"), edu.get("title"), edu.get("level"), edu.get("status") or edu.get("school")]
                    if value
                )
                y -= text_height(details, main_w, body_size, leading, True) + 6.0 * scale
        return y

    content_scale = 0.78
    for candidate in (1.0, 0.96, 0.92, 0.88, 0.84, 0.80, 0.78):
        if main_bottom(candidate) >= bottom:
            content_scale = candidate
            break

    body_size, leading = 7.7 * content_scale, 11.4 * content_scale
    meta_size, meta_leading = 7.0 * content_scale, 10.0 * content_scale
    title_size, title_leading = 8.0 * content_scale, 10.4 * content_scale

    draw_portrait()

    # Identity header, aligned with the reference CV.
    header_x = main_x + 40.0
    name_y, target_y = _identity_baselines(top)
    set_font(34.0, False, primary)
    c.drawString(header_x, name_y, "Facundo Varas")
    target = str(cv.get("title", "CV personnalisé")).upper()
    target_size = 11.0
    target_max_w = min(main_w - 34.0, IDENTITY_TITLE_MAX_WIDTH)
    while target_size > IDENTITY_TITLE_MIN_SIZE and stringWidth(target, regular_font, target_size) + max(0, len(target) - 1) * IDENTITY_TITLE_TRACKING > target_max_w:
        target_size -= 0.5
    target_lines = wrap_tracked_title(target, max_width=target_max_w, size=target_size, tracking=IDENTITY_TITLE_TRACKING)
    if len(target_lines) > 1:
        target_y += 6.5 * (len(target_lines) - 1)
    for line_index, target_line in enumerate(target_lines):
        draw_tracked(target_line, main_x + 34.0, target_y - line_index * 13.0, target_size, IDENTITY_TITLE_TRACKING, secondary)

    # Sidebar intentionally begins lower than the portrait, as in the model.
    sidebar_scale = 1.0
    side_body, side_leading = 7.5 * sidebar_scale, 11.3 * sidebar_scale
    side_contact, contact_leading = 7.1 * sidebar_scale, 10.2 * sidebar_scale
    y_side = top - 190.0
    y_side = draw_section("Profil", sidebar_x, y_side, sidebar_scale)
    y_side = draw_wrapped(cv.get("profile", ""), sidebar_x, y_side, sidebar_inner_w, side_body, side_leading, color=primary)
    y_side -= 28.0
    y_side = draw_section("Contact", sidebar_x, y_side, sidebar_scale)
    contact_rows = [
        ("email", contact.get("email")),
        ("tel", contact.get("phone")),
        ("lieu", cv.get("location")),
        ("web", contact.get("portfolio")),
        ("git", contact.get("github")),
    ]
    for _label, value in contact_rows:
        if not value:
            continue
        c.setFillColor(accent)
        c.rect(sidebar_x, y_side + 1.0, 4.0, 4.0, stroke=0, fill=1)
        y_side = draw_wrapped(str(value), sidebar_x + 10.0, y_side, sidebar_inner_w - 10.0, side_contact, contact_leading, color=secondary)
        y_side -= 4.0
    if cv.get("languages"):
        y_side -= 16.0
        y_side = draw_section("Langues", sidebar_x, y_side, sidebar_scale)
        for lang in cv.get("languages", []):
            y_side = draw_wrapped(
                f"{lang.get('name')} : {lang.get('level')}",
                sidebar_x,
                y_side,
                sidebar_inner_w,
                side_body,
                side_leading,
                color=secondary,
            )
            y_side -= 3.0

    # Main content.
    y = top - 137.0
    y = draw_section("Compétences techniques", main_x, y, content_scale)
    for skill in cv.get("skills", []):
        label = str(skill.get("title", ""))
        text = f"{label} : {', '.join(skill.get('items', []))}"
        y = draw_wrapped(text, main_x, y, main_w, body_size, leading, color=primary)
        y -= 6.5 * content_scale
    y -= 22.0 * content_scale
    y = draw_section("Expériences", main_x, y, content_scale)
    for exp in cv.get("experiences", [])[:4]:
        item_top = y
        meta_y = draw_wrapped(str(exp.get("period", "")), main_x, item_top, meta_w, meta_size, meta_leading, bold=True, color=primary)
        meta_y -= 3.0 * content_scale
        meta_y = draw_wrapped(str(exp.get("organization", "")), main_x, meta_y, meta_w, meta_size, meta_leading, color=secondary)

        desc_y = draw_wrapped(
            str(exp.get("title", "")).upper(), desc_x, item_top, desc_w, title_size, title_leading, bold=True, color=primary
        )
        desc_y -= 4.0 * content_scale
        for bullet in exp.get("bullets", [])[:3]:
            desc_y = draw_wrapped(str(bullet), desc_x, desc_y, desc_w, body_size, leading, color=secondary, bullet=True)
            desc_y -= 2.5 * content_scale
        y = min(meta_y, desc_y) - 17.0 * content_scale

    projects = cv.get("projects", [])
    if projects:
        y = draw_section("Projet personnel", main_x, y, content_scale)
        project = projects[0]
        y = draw_wrapped(str(project.get("title", "")), main_x, y, main_w, title_size, title_leading, bold=True, color=primary)
        y -= 4.0 * content_scale
        project_text = f"{project.get('description', '')} - {', '.join(project.get('technologies', []))}"
        y = draw_wrapped(project_text, main_x, y, main_w, body_size, leading, color=secondary)

    if cv.get("education"):
        y -= 22.0 * content_scale
        y = draw_section("Formation", main_x, y, content_scale)
        for edu in cv.get("education", [])[:2]:
            details = " - ".join(
                str(value)
                for value in [edu.get("year"), edu.get("title"), edu.get("level"), edu.get("status") or edu.get("school")]
                if value
            )
            y = draw_wrapped(details, main_x, y, main_w, body_size, leading, bold=True, color=primary)
            y -= 6.0 * content_scale

    c.showPage()
    c.save()
