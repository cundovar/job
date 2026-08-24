from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_DESIGN_SYSTEM = "config/cv_design_system.json"


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


def cv_to_html(final_cv: Dict[str, Any], design_system_path: str | Path = DEFAULT_DESIGN_SYSTEM) -> str:
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

    sidebar = ["<div class='portrait'>FV</div>", _section("Profil"), f"<p>{escape(cv.get('profile', ''))}</p>"]
    sidebar.append(_section("Contact"))
    for icon, text in contact_items:
        if text:
            sidebar.append(f"<div class='contact-item'><span>{escape(icon)}</span><p>{escape(str(text))}</p></div>")
    if cv.get("languages"):
        sidebar.append(_section("Langues"))
        for lang in cv.get("languages", []):
            sidebar.append(f"<p><strong>{escape(str(lang.get('name', '')))}</strong> — {escape(str(lang.get('level', '')))}</p>")
    if cv.get("education"):
        sidebar.append(_section("Formation"))
        for edu in cv.get("education", [])[:2]:
            details = " — ".join(str(x) for x in [edu.get("year"), edu.get("title"), edu.get("level"), edu.get("status") or edu.get("school")] if x)
            sidebar.append(f"<p>{escape(details)}</p>")

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
  .page {{ width: 794px; min-height: 1123px; margin: 0 auto; background: {bg}; padding: 27px 28px 26px 22px; display: grid; grid-template-columns: 24% 7% 69%; }}
  aside {{ grid-column: 1; padding-top: 4px; color: {secondary}; }}
  main {{ grid-column: 3; }}
  header {{ height: 128px; padding-top: 10px; }}
  h1 {{ margin: 0 0 8px; font-size: 25pt; font-weight: 400; letter-spacing: .01em; line-height: 1.1; }}
  .target-title, h2 {{ text-transform: uppercase; letter-spacing: .32em; font-weight: 400; color: {primary}; }}
  .target-title {{ font-size: 9pt; line-height: 1.35; }}
  h2 {{ margin: 24px 0 0; font-size: 8.3pt; line-height: 1.2; }}
  .section-line {{ width: 31px; height: 3px; background: {accent}; margin: 8px 0 12px; }}
  p, li {{ font-size: 7.1pt; line-height: 1.42; margin: 0 0 7px; }}
  .portrait {{ width: 82px; height: 82px; border-radius: 50%; background: #d9dddc; color: {primary}; display:flex; align-items:center; justify-content:center; font-size: 18px; margin-bottom: 24px; filter: grayscale(1); }}
  .contact-item {{ display: grid; grid-template-columns: 9px 1fr; gap: 5px; align-items: start; margin-bottom: 6px; }}
  .contact-item span {{ font-size: 7px; color: {accent}; }}
  .contact-item p {{ font-size: 6.7pt; line-height: 1.4; overflow-wrap: anywhere; }}
  .skill strong {{ font-weight: 700; }}
  .experience {{ display: grid; grid-template-columns: 18% 82%; gap: 14px; margin-bottom: 15px; }}
  .meta, .meta strong {{ color: {secondary}; font-size: 6.5pt; line-height: 1.3; font-weight: 600; }}
  h3 {{ margin: 0 0 6px; font-size: 7.2pt; line-height: 1.2; font-weight: 700; text-transform: uppercase; letter-spacing: .01em; }}
  ul {{ margin: 0 0 0 9px; padding: 0; }}
  li {{ padding-left: 0; margin-bottom: 4px; }}
  .project span {{ color: {secondary}; }}
  @media (max-width: 820px) {{ .page {{ width: 100%; min-height: auto; grid-template-columns: 1fr; padding: 24px; }} aside, main {{ grid-column: 1; }} header {{ height: auto; margin-bottom: 20px; }} }}
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


def cv_to_pdf(final_cv: Dict[str, Any], output_path: str | Path, design_system_path: str | Path = DEFAULT_DESIGN_SYSTEM) -> None:
    """Create a one-page, Canva-style PDF using ReportLab.

    The HTML preview is the richer reference, but this PDF is directly attachable.
    It intentionally follows the provided monochrome/two-column design system.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    design = _load_design_system(design_system_path)
    cv = final_cv.get("cv", {})
    contact = cv.get("contact", {})
    colors_cfg = design.get("colors", {})
    primary = colors.HexColor(colors_cfg.get("text_primary", "#111111"))
    secondary = colors.HexColor(colors_cfg.get("text_secondary", "#606665"))
    accent = colors.HexColor(colors_cfg.get("accent", "#788481"))

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out), pagesize=A4)
    width, height = A4
    scale = width / 794.0
    pad = design.get("spacing", {}).get("page_padding_px", {"top": 27, "right": 28, "bottom": 26, "left": 22})
    left = pad.get("left", 22) * scale
    right = width - pad.get("right", 28) * scale
    top = height - pad.get("top", 27) * scale
    sidebar_w = width * 0.24
    gutter = width * 0.07
    main_x = left + sidebar_w + gutter
    main_w = right - main_x
    sidebar_x = left
    sidebar_inner_w = sidebar_w - 6

    # The Canva measurements are estimated from thumbnails and are too small
    # when translated literally to a generated PDF. These readable values keep
    # the same proportions while filling the A4 page vertically.
    NAME_SIZE = 25
    TARGET_SIZE = 9
    SECTION_SIZE = 8.3
    BODY_SIZE = 7.1
    BODY_LEADING = 9.6
    CONTACT_SIZE = 6.7
    CONTACT_LEADING = 8.4
    META_SIZE = 6.5
    EXP_TITLE_SIZE = 7.2

    def set_font(size: float, bold: bool = False, color=primary):
        c.setFillColor(color)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)

    def wrap(text: str, max_w: float, size: float, bold: bool = False) -> List[str]:
        font = "Helvetica-Bold" if bold else "Helvetica"
        words = str(text).split()
        lines: List[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if stringWidth(candidate, font, size) <= max_w or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    def draw_wrapped(text: str, x: float, y: float, max_w: float, size: float, leading: float, bold: bool = False, color=primary, bullet: bool = False) -> float:
        set_font(size, bold, color)
        for line in wrap(text, max_w - (7 if bullet else 0), size, bold):
            prefix = "• " if bullet else ""
            c.drawString(x, y, prefix + line)
            y -= leading
        return y

    def section(title: str, x: float, y: float) -> float:
        set_font(SECTION_SIZE, False, primary)
        c.drawString(x, y, title.upper())
        y -= 8
        c.setFillColor(accent)
        c.rect(x, y, 31 * scale, 3 * scale, stroke=0, fill=1)
        return y - 13

    # Portrait placeholder
    c.setFillColor(colors.HexColor("#D9DDDC"))
    d = 82 * scale
    c.circle(sidebar_x + d / 2, top - d / 2, d / 2, stroke=0, fill=1)
    set_font(16, False, primary)
    c.drawCentredString(sidebar_x + d / 2, top - d / 2 - 5, "FV")

    # Identity header
    y_main = top - 8
    set_font(NAME_SIZE, False, primary)
    c.drawString(main_x, y_main, "Facundo Varas")
    y_main -= 22
    set_font(TARGET_SIZE, False, primary)
    c.drawString(main_x, y_main, cv.get("title", "CV personnalisé").upper())

    # Sidebar
    y = top - d - 22
    y = section("Profil", sidebar_x, y)
    y = draw_wrapped(cv.get("profile", ""), sidebar_x, y, sidebar_inner_w, BODY_SIZE, BODY_LEADING, color=secondary)
    y -= 13
    y = section("Contact", sidebar_x, y)
    for text in [contact.get("email"), contact.get("phone"), cv.get("location"), contact.get("portfolio"), contact.get("github")]:
        if text:
            y = draw_wrapped(str(text), sidebar_x + 12, y, sidebar_inner_w - 12, CONTACT_SIZE, CONTACT_LEADING, color=secondary)
            y -= 3
    y -= 10
    y = section("Langues", sidebar_x, y)
    for lang in cv.get("languages", []):
        y = draw_wrapped(f"{lang.get('name')} — {lang.get('level')}", sidebar_x, y, sidebar_inner_w, BODY_SIZE, BODY_LEADING, color=secondary)
    y -= 13
    y = section("Formation", sidebar_x, y)
    for edu in cv.get("education", [])[:2]:
        details = " — ".join(str(x) for x in [edu.get("year"), edu.get("title"), edu.get("level"), edu.get("status") or edu.get("school")] if x)
        y = draw_wrapped(details, sidebar_x, y, sidebar_inner_w, BODY_SIZE, BODY_LEADING, color=secondary)
        y -= 7

    # Main content
    y = top - 128 * scale
    y = section("Compétences", main_x, y)
    for skill in cv.get("skills", []):
        line = f"{skill.get('title')}: {', '.join(skill.get('items', []))}"
        y = draw_wrapped(line, main_x, y, main_w, BODY_SIZE, BODY_LEADING, color=primary)
        y -= 5
    y -= 12
    y = section("Expériences", main_x, y)
    meta_w = main_w * 0.18
    desc_x = main_x + meta_w + 10
    desc_w = main_w - meta_w - 10
    for exp in cv.get("experiences", [])[:4]:
        item_top = y
        draw_wrapped(str(exp.get("period", "")), main_x, item_top, meta_w, META_SIZE, 8.1, bold=True, color=secondary)
        draw_wrapped(str(exp.get("organization", "")), main_x, item_top - 10, meta_w, META_SIZE, 8.1, color=secondary)
        set_font(EXP_TITLE_SIZE, True, primary)
        c.drawString(desc_x, y, str(exp.get("title", "")).upper()[:90])
        y -= 11
        for b in exp.get("bullets", [])[:3]:
            y = draw_wrapped(str(b), desc_x + 7, y, desc_w - 7, BODY_SIZE, BODY_LEADING, color=primary, bullet=True)
        y -= 15
    projects = cv.get("projects", [])
    if projects:
        y = section("Projets personnels", main_x, y)
        for project in projects[:1]:
            y = draw_wrapped(str(project.get("title", "")), main_x, y, main_w, EXP_TITLE_SIZE, BODY_LEADING, bold=True, color=primary)
            text = f"{project.get('description', '')} — {', '.join(project.get('technologies', []))}"
            y = draw_wrapped(text, main_x, y, main_w, BODY_SIZE, BODY_LEADING, color=primary)

    c.showPage()
    c.save()
