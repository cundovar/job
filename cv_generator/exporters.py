from __future__ import annotations

import json
import base64
import mimetypes
import re
from html import escape
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

from .layout import (
    IDENTITY_TITLE_MAX_WIDTH,
    IDENTITY_TITLE_MIN_SIZE,
    IDENTITY_TITLE_TRACKING,
    sparse_main_vertical_offset,
    wrap_tracked_title,
)


DEFAULT_DESIGN_SYSTEM = "config/cv_design_system.json"
DEFAULT_PORTRAIT = Path(__file__).resolve().parent.parent / "assets" / "cv" / "facundo-varas.jpg"
PDF_PORTRAIT_DIAMETER = 119.0


def _project_text(project) -> str:
    description = str(project.get("description", "")).strip()
    tech = ", ".join(project.get("technologies", []))
    if description and tech:
        return f"{description} \u00b7 {tech}"
    return description or tech


def _display_url(value: Any) -> str:
    raw = str(value or "").strip()
    parsed = urlparse(raw)
    label = f"{parsed.netloc}{parsed.path}" if parsed.netloc else raw
    return label.removeprefix("www.").rstrip("/")


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
        for link in exp.get("links", [])[:2]:
            lines.append(str(link))
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
            for link in project.get("links", [])[:1]:
                lines.append(str(link))
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

    main = [_section("Compétences")]
    for section in cv.get("skills", []):
        main.append(
            f"<p class='skill'><strong>{escape(section.get('title', ''))}</strong>: "
            f"{escape(', '.join(section.get('items', [])))}</p>"
        )
    main.append(_section("Expériences"))
    for exp in cv.get("experiences", []):
        bullets = "".join(f"<li>{escape(str(b))}</li>" for b in exp.get("bullets", [])[:4])
        exp_link_html = "".join(
            f"<br><a class='record-link' href='{escape(str(link), quote=True)}'>{escape(_display_url(link))}</a>"
            for link in exp.get("links", [])[:2]
        )
        main.append(
            "<article class='experience'>"
            f"<div class='meta'><strong>{escape(str(exp.get('period', '')))}</strong><br>{escape(str(exp.get('organization', '')))}{exp_link_html}</div>"
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
            project_link = next(iter(project.get("links", [])[:1]), "")
            project_link_html = (
                f" <a class='record-link' href='{escape(str(project_link), quote=True)}'>{escape(_display_url(project_link))}</a>"
                if project_link else ""
            )
            main.append(
                f"<p class='project'><strong>{escape(str(project.get('title', '')))}</strong> — "
                f"{escape(str(project.get('description', '')))}"
                f" <span>{escape(tech)}</span>{project_link_html}</p>"
            )
    if cv.get("education"):
        main.append(_section("Formation"))
        for edu in cv.get("education", []):
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
  .main-body.sparse {{ padding-top: 70px; }}
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
  .record-link {{ color: {accent}; overflow-wrap: anywhere; }}
  @media (max-width: 820px) {{ .page {{ width: 100%; min-height: auto; grid-template-columns: 1fr; padding: 24px; }} aside, main {{ grid-column: 1; }} header {{ height: auto; margin-bottom: 20px; justify-content: flex-start; }} .main-body.sparse {{ padding-top: 0; }} }}
</style>
</head>
<body>
<div class="page">
  <aside>{''.join(sidebar)}</aside>
  <main>
    <header>
      <h1>Facundo Varas</h1>
      <div class="target-title">{escape(cv.get('title', 'CV personnalisé'))}</div>
    </header>
    <div class="main-body{' sparse' if len(cv.get('experiences', [])) <= 2 and not projects else ''}">{''.join(main)}</div>
  </main>
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
    """CV une page, design « sidebar teintée » (validé par Cundo le 20/10/2026).

    Le rendu vit dans cv_pdf_design ; design_system_path est conservé pour la
    compatibilité des appels existants. L'ancienne mise en page Canva reste
    lisible dans l'historique git (commit 93ac5b6 et avant).
    """
    from .cv_pdf_design import render_cv_pdf

    render_cv_pdf(final_cv, output_path, portrait_path)


def _parse_lettre_markdown(raw: str) -> tuple[str, str, list[str]]:
    """Découpe une lettre markdown : ligne de lieu/date, objet, paragraphes."""
    date_re = re.compile(r"^\[?([A-ZÀ-Ý][\wà-ÿ'’ \-]*,\s*le\s+[^\]]+)\]?$")
    date_line, objet, blocks, current = "", "", [], []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            if current:
                blocks.append(" ".join(current))
                current = []
            continue
        if line.lower().startswith("objet :"):
            objet = line
            continue
        if not objet and not blocks and not current:
            match = date_re.match(line)
            if match:
                date_line = match.group(1).strip()
                continue
        current.append(line)
    if current:
        blocks.append(" ".join(current))
    return date_line, objet, blocks


_LETTRE_CLOSING_RE = re.compile(
    r"^(bien\s+)?cordialement|^bien\s+à\s+vous|^respectueusement|^(sincères\s+|meilleures\s+)?salutations"
    r"|^avec\s+mes\s+(meilleures|sincères)",
    re.IGNORECASE,
)
_LETTRE_DATE_RE = re.compile(r"^\[?([A-ZÀ-Ý][\wà-ÿ'’ \-]*,\s*le\s+[^\]]+)\]?$")


def _lettre_blocks(raw: str) -> list[list[str]]:
    """Blocs séparés par une ligne vide, lignes conservées.

    Un titre markdown « # Lettre de motivation » est un reste de gabarit, pas
    du contenu : on le retire. Tout autre titre garde son texte, sans les #.
    """
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("#"):
            line = line.lstrip("#").strip()
            if line.lower() == "lettre de motivation":
                line = ""
        if not line:
            if current:
                blocks.append(current)
                current = []
            continue
        current.append(line)
    if current:
        blocks.append(current)
    return blocks


def _is_signature_block(lines: list[str]) -> bool:
    return len(lines) <= 3 and all(len(line) <= 60 and not line.endswith(".") for line in lines)


def _parse_lettre_structure(raw: str) -> Dict[str, Any]:
    """Découpe une lettre en parties d'une lettre française.

    Rien n'est réécrit ni déplacé hors de sa partie : on reconnaît seulement
    la date, le destinataire (ce qui précède l'objet), l'objet, la formule
    d'appel, le corps, la formule de politesse et la signature. Sans ligne
    « Objet : », rien n'est pris pour un destinataire.
    """
    blocks = _lettre_blocks(raw)
    has_objet = any(line.lower().startswith("objet") for block in blocks for line in block)
    parts: Dict[str, Any] = {
        "date": "", "recipient": [], "objet": "", "salutation": "",
        "body": [], "closing": [], "signature": [],
    }
    remaining: list[list[str]] = []
    before_objet = True
    for block in blocks:
        if not before_objet:
            remaining.append(block)
            continue
        rest: list[str] = []
        for line in block:
            if before_objet and line.lower().startswith("objet"):
                parts["objet"] = line
                before_objet = False
                continue
            if before_objet and not parts["date"] and _LETTRE_DATE_RE.match(line):
                parts["date"] = _LETTRE_DATE_RE.match(line).group(1).strip()
                continue
            if before_objet and has_objet:
                parts["recipient"].append(line)
                continue
            rest.append(line)
        if rest:
            remaining.append(rest)

    if remaining and len(remaining[0]) == 1 and remaining[0][0].endswith(",") and len(remaining[0][0]) <= 60:
        parts["salutation"] = remaining.pop(0)[0]

    closing_index = next(
        (index for index in range(len(remaining) - 1, -1, -1)
         if _LETTRE_CLOSING_RE.match(remaining[index][0]) and len(remaining[index][0]) <= 60),
        None,
    )
    if closing_index is not None:
        tail = remaining[closing_index:]
        remaining = remaining[:closing_index]
        parts["closing"] = tail[0]
        parts["signature"] = [line for block in tail[1:] for line in block]
    elif remaining and len(remaining) > 1 and _is_signature_block(remaining[-1]):
        parts["signature"] = remaining.pop()

    parts["body"] = [" ".join(block) for block in remaining]
    return parts


def _lettre_inline(text: str) -> str:
    """Markdown en ligne → balises ReportLab, après échappement."""
    from html import escape as _xml_escape

    out = _xml_escape(str(text), quote=False)
    out = re.sub(r"\[([^\]]+)\]\((?:[^)]+)\)", r"\1", out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", out)
    out = re.sub(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)", r"<i>\1</i>", out)
    return out


_LETTRE_FONT_CANDIDATES = (
    # (famille, dossier, regular, bold, italic, bold italic) — italiques facultatives.
    ("LettreSans", "/usr/share/fonts/truetype/liberation",
     "LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf",
     "LiberationSans-Italic.ttf", "LiberationSans-BoldItalic.ttf"),
    ("LettreDejaVu", "/usr/share/fonts/truetype/dejavu",
     "DejaVuSans.ttf", "DejaVuSans-Bold.ttf",
     "DejaVuSans-Oblique.ttf", "DejaVuSans-BoldOblique.ttf"),
)


def _lettre_fonts(pdfmetrics: Any, ttfont: Any) -> tuple[str, str]:
    """Première police disponible sur la machine, Helvetica sinon.

    Le VPS, le poste et l'image Docker n'ont pas les mêmes polices : une
    italique absente ne doit pas faire retomber toute la lettre.
    """
    for family, folder, regular, bold, italic, bold_italic in _LETTRE_FONT_CANDIDATES:
        base = Path(folder)
        if not (base / regular).is_file() or not (base / bold).is_file():
            continue
        try:
            pdfmetrics.registerFont(ttfont(family, str(base / regular)))
            pdfmetrics.registerFont(ttfont(f"{family}-Bold", str(base / bold)))
            italic_name, bold_italic_name = family, f"{family}-Bold"
            if (base / italic).is_file():
                pdfmetrics.registerFont(ttfont(f"{family}-Italic", str(base / italic)))
                italic_name = f"{family}-Italic"
            if (base / bold_italic).is_file():
                pdfmetrics.registerFont(ttfont(f"{family}-BoldItalic", str(base / bold_italic)))
                bold_italic_name = f"{family}-BoldItalic"
            pdfmetrics.registerFontFamily(
                family, normal=family, bold=f"{family}-Bold",
                italic=italic_name, boldItalic=bold_italic_name,
            )
            return family, f"{family}-Bold"
        except Exception:
            continue
    return "Helvetica", "Helvetica-Bold"


def lettre_to_pdf(
    markdown_path: str | Path,
    output_path: str | Path,
    design_system_path: str | Path = DEFAULT_DESIGN_SYSTEM,
    candidate_name: str = "Facundo Varas",
    contact_line: str = "Paris 20e · contact@varascundo.com · varascundo.com",
) -> None:
    """Lettre de motivation en PDF A4, mise en page de lettre française.

    Le markdown est la source : en-tête candidat, destinataire et date à
    droite, objet, corps justifié, formule de politesse et signature à
    droite. Le texte n'est jamais modifié, seulement placé.
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_JUSTIFY, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer

    design = _load_design_system(design_system_path)
    colors_cfg = design.get("colors", {})
    primary = colors.HexColor(colors_cfg.get("text_primary", "#111111"))
    secondary = colors.HexColor(colors_cfg.get("text_secondary", "#606665"))
    accent = colors.HexColor(colors_cfg.get("accent", "#788481"))

    regular_font, bold_font = _lettre_fonts(pdfmetrics, TTFont)

    parts = _parse_lettre_structure(Path(markdown_path).read_text(encoding="utf-8"))

    page_width, _ = A4
    margin = 62
    frame_width = page_width - 2 * margin
    # Destinataire et signature commencent à mi-page, comme sur une lettre papier.
    half = frame_width * 0.52

    def style(name: str, **kwargs: Any) -> ParagraphStyle:
        base = {"fontName": regular_font, "fontSize": 10.5, "leading": 15, "textColor": primary}
        base.update(kwargs)
        return ParagraphStyle(name, **base)

    style_name = style("lettre-name", fontSize=21, leading=24, letterSpacing=0.2)
    style_contact = style("lettre-contact", fontSize=8.8, leading=12, textColor=secondary)
    style_recipient = style("lettre-recipient", leftIndent=half, leading=14.5)
    style_date = style("lettre-date", alignment=TA_RIGHT, textColor=secondary, fontSize=10)
    style_objet = style("lettre-objet", fontName=bold_font)
    style_body = style("lettre-body", alignment=TA_JUSTIFY, leading=15.8, spaceAfter=9)
    style_closing = style("lettre-closing", leftIndent=half)
    style_signature = style("lettre-signature", leftIndent=half, fontName=bold_font)
    style_signature_extra = style("lettre-signature-extra", leftIndent=half, textColor=secondary, fontSize=9.5)

    doc = SimpleDocTemplate(str(output_path), pagesize=A4,
                            leftMargin=margin, rightMargin=margin, topMargin=54, bottomMargin=54,
                            title="Lettre de motivation", author=candidate_name)
    story: list = [
        Paragraph(_lettre_inline(candidate_name), style_name),
        Spacer(1, 3),
        Paragraph(_lettre_inline(contact_line), style_contact),
        Spacer(1, 10),
        HRFlowable(width="100%", thickness=0.6, color=accent),
        Spacer(1, 26),
    ]
    if parts["recipient"]:
        for line in parts["recipient"]:
            story.append(Paragraph(_lettre_inline(line), style_recipient))
        story.append(Spacer(1, 18))
    if parts["date"]:
        story.append(Paragraph(_lettre_inline(parts["date"]), style_date))
        story.append(Spacer(1, 22))
    if parts["objet"]:
        label, _, rest = parts["objet"].partition(":")
        objet_html = _lettre_inline(parts["objet"])
        if rest:
            accent_hex = "#" + accent.hexval()[2:]
            objet_html = (f'<font color="{accent_hex}">{_lettre_inline(label.strip())} :</font> '
                          f"{_lettre_inline(rest.strip())}")
        story.append(Paragraph(objet_html, style_objet))
        story.append(Spacer(1, 20))
    if parts["salutation"]:
        story.append(Paragraph(_lettre_inline(parts["salutation"]), style_body))
    for block in parts["body"]:
        story.append(Paragraph(_lettre_inline(block), style_body))

    ending: list = []
    if parts["closing"]:
        ending.append(Spacer(1, 10))
        for line in parts["closing"]:
            ending.append(Paragraph(_lettre_inline(line), style_closing))
    if parts["signature"]:
        ending.append(Spacer(1, 14))
        ending.append(Paragraph(_lettre_inline(parts["signature"][0]), style_signature))
        for line in parts["signature"][1:]:
            ending.append(Paragraph(_lettre_inline(line), style_signature_extra))
    if ending:
        # La formule et la signature ne se séparent jamais sur deux pages.
        story.append(KeepTogether(ending))
    doc.build(story)
