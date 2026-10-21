"""CV PDF « sidebar teintée » (design validé par Cundo le 20/10/2026).

Une page A4 : colonne gauche teintée (photo, profil, contact, réalisations en
ligne, langues) et colonne principale (identité, compétences en deux colonnes,
expériences à filet vertical, projets, formation). Tous les liens sont
cliquables.

Le rendu ne choisit pas le contenu : il dessine ce que l'agent a retenu. Seule
la rubrique « Réalisations en ligne » est décidée ici, à partir des liens déjà
présents dans le CV : elle n'apparaît que s'il y a au moins deux liens vers des
travaux publics, jamais pour les variantes accueil, logistique et surveillance,
et disparaît si la colonne gauche manque de place. Un CV peut
la forcer ou l'interdire avec ``cv["show_online_work"]`` (True/False).

La mise en page est mesurée avant d'être dessinée : la colonne principale se
resserre par petits pas jusqu'à tenir sur la page.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple
from urllib.parse import urlparse

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

# Palette : vert sapin sobre sur fond blanc, colonne gauche légèrement teintée.
INK = "#1D2321"
SOFT = "#58615E"
BODY = "#2F3634"
ACCENT = "#2F6F62"
TINT = "#EEF3F1"
LINE = "#D6DFDC"

# Variantes où des liens vers des sites web n'apportent rien au recruteur
# (accueil, logistique, surveillance) : pas de rubrique « Réalisations en ligne ».
NON_DIGITAL_VARIANTS = {"accueil", "logistique", "surveillance"}

_FONT_CACHE: Dict[str, Tuple[str, str, str, str]] = {}


def _display_url(value: Any) -> str:
    raw = str(value or "").strip()
    parsed = urlparse(raw)
    label = f"{parsed.netloc}{parsed.path}" if parsed.netloc else raw
    return label.removeprefix("www.").rstrip("/")


def _href(value: Any, kind: str = "web") -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if kind == "email":
        return f"mailto:{raw}"
    if kind == "tel":
        digits = "".join(ch for ch in raw if ch.isdigit() or ch == "+")
        if digits.startswith("0") and len(digits) == 10:
            digits = "+33" + digits[1:]
        return f"tel:{digits}"
    return raw if raw.startswith(("http://", "https://", "mailto:")) else f"https://{raw}"


def _register_fonts(pdfmetrics: Any, ttfont: Any) -> Tuple[str, str, str, str]:
    """(light, regular, semibold, bold) : Inter embarquée, DejaVu, Helvetica."""
    if "fonts" in _FONT_CACHE:
        return _FONT_CACHE["fonts"]
    candidates = [
        ("CVInter", FONT_DIR, ("Inter-Light.ttf", "Inter-Regular.ttf", "Inter-SemiBold.ttf", "Inter-Bold.ttf")),
        ("CVDejaVu", Path("/usr/share/fonts/truetype/dejavu"),
         ("DejaVuSans-ExtraLight.ttf", "DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf")),
    ]
    result = ("Helvetica", "Helvetica", "Helvetica-Bold", "Helvetica-Bold")
    for family, folder, files in candidates:
        if not all((folder / name).is_file() for name in files[1:]):
            continue
        try:
            names = []
            for weight, name in zip(("Light", "Regular", "SemiBold", "Bold"), files):
                path = folder / name
                if not path.is_file():
                    path = folder / files[1]
                font_name = f"{family}-{weight}"
                pdfmetrics.registerFont(ttfont(font_name, str(path)))
                names.append(font_name)
            result = tuple(names)  # type: ignore[assignment]
            break
        except Exception:
            continue
    _FONT_CACHE["fonts"] = result
    return result


def _split_title(title: str) -> Tuple[str, str]:
    """« DevDoc — plateforme … » → (« DevDoc », « plateforme … »)."""
    for sep in (" — ", " – ", " - "):
        if sep in title:
            head, tail = title.split(sep, 1)
            return head.strip(), tail.strip()
    return title.strip(), ""


def _education_parts(edu: Dict[str, Any]) -> Tuple[str, str, str]:
    """(année, intitulé, complément) depuis les deux formes connues."""
    year = str(edu.get("year") or "").strip()
    title = str(edu.get("title") or "").strip()
    extra = " — ".join(str(v) for v in (edu.get("level"), edu.get("status") or edu.get("school")) if v)
    if not year:
        match = re.match(r"^(\d{4})\s*[—–-]\s*(.+)$", title)
        if match:
            year, title = match.group(1), match.group(2)
    if not extra and " — " in title:
        title, extra = title.rsplit(" — ", 1)
    return year, title, extra


# « Réalisations en ligne » (décision Cundo 21/10/2026) : nat.varascundo.com
# n'y figure jamais ; le guide Chant d'Orties y est mis en avant dès que la
# mission apparaît sur le CV. Le lien reste visible dans le bloc d'expérience.
ONLINE_WORK_EXCLUDED = {"nat.varascundo.com"}
CHANT_ORTIES_GUIDE = ("Chant d'Orties — guide", "https://tuto-des-orties.varascundo.com/")


def _online_work(cv: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Liens vers des travaux publics, dans l'ordre du CV, sans doublon."""
    items: List[Tuple[str, str]] = []
    seen = set(ONLINE_WORK_EXCLUDED)

    def add(label: str, url: str) -> None:
        key = _display_url(url).split("/")[0]
        if url and key not in seen:
            seen.add(key)
            items.append((label, url))

    if any("orties" in str(exp.get("organization", "")).lower() for exp in cv.get("experiences", [])):
        add(*CHANT_ORTIES_GUIDE)
    seen.add("chantdorties.pages-perso.free.fr")

    for exp in cv.get("experiences", []):
        for link in exp.get("links", [])[:2]:
            add(_display_url(link).split("/")[0], str(link))
    for project in cv.get("projects", [])[:2]:
        links = project.get("links", [])
        if links:
            add(_split_title(str(project.get("title", "")))[0] or _display_url(links[0]), str(links[-1]))
    return items[:5]


def render_cv_pdf(
    final_cv: Dict[str, Any],
    output_path: str | Path,
    portrait_path: str | Path,
) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    cv = final_cv.get("cv", {})
    contact = cv.get("contact", {}) or {}
    light, regular, semibold, bold = _register_fonts(pdfmetrics, TTFont)
    ink, soft, body_c, accent, tint, line_c = (colors.HexColor(v) for v in (INK, SOFT, BODY, ACCENT, TINT, LINE))

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out), pagesize=A4)
    c.setTitle(f"CV Facundo Varas — {cv.get('title', '')}".strip(" —"))
    c.setAuthor("Facundo Varas")
    width, height = A4
    mm = 2.8346

    side_w = 64 * mm
    side_x, side_pad_r = 9 * mm, 7 * mm
    side_inner = side_w - side_x - side_pad_r
    main_x = side_w + 9 * mm
    main_right = width - 11 * mm
    main_w = main_right - main_x
    page_bottom = 9 * mm

    # ------------------------------------------------------------------ outils
    def wrap(text: str, max_w: float, font: str, size: float) -> List[str]:
        words = str(text or "").replace(" ", " ").split()
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

    class Pen:
        """Dessine (draw=True) ou mesure seulement (draw=False)."""

        def __init__(self, draw: bool) -> None:
            self.draw = draw

        def text(self, s: str, x: float, y: float, font: str, size: float, color, url: str | None = None) -> float:
            w = stringWidth(s, font, size)
            if self.draw:
                c.setFillColor(color)
                c.setFont(font, size)
                c.drawString(x, y, s)
                if url:
                    c.linkURL(url, (x, y - size * 0.25, x + w, y + size * 0.9), relative=0)
            return w

        def para(self, s: str, x: float, y: float, max_w: float, font: str, size: float, leading: float,
                 color, url: str | None = None) -> float:
            for ln in wrap(s, max_w, font, size):
                self.text(ln, x, y, font, size, color, url)
                y -= leading
            return y

        def tracked(self, s: str, x: float, y: float, font: str, size: float, tracking: float, color) -> None:
            if not self.draw:
                return
            c.saveState()
            t = c.beginText(x, y)
            t.setFont(font, size)
            t.setFillColor(color)
            t.setCharSpace(tracking)
            t.textLine(s.upper())
            c.drawText(t)
            c.restoreState()

        def hline(self, x1: float, x2: float, y: float, color, w: float = 0.7) -> None:
            if self.draw:
                c.setStrokeColor(color)
                c.setLineWidth(w)
                c.line(x1, y, x2, y)

        def vline(self, x: float, y1: float, y2: float, color, w: float = 1.4) -> None:
            if self.draw:
                c.setStrokeColor(color)
                c.setLineWidth(w)
                c.line(x, y1, x, y2)

    def heading(pen: Pen, title: str, x: float, y: float, w: float, s: float) -> float:
        size = 7.4 * s
        pen.tracked(title, x, y, bold, size, 1.9 * s, accent)
        y -= 3.6 * s
        pen.hline(x, x + w, y, line_c)
        return y - 10.5 * s

    # ------------------------------------------------------- colonne principale
    def main_column(pen: Pen, s: float) -> float:
        body, lead = 8.1 * s, 10.9 * s
        small, small_lead = 7.6 * s, 10.0 * s
        y = height - 11 * mm - 24
        # Identité : prénom léger, nom gras, cible en accent.
        name_size = 25
        x = main_x
        x += pen.text("Facundo ", x, y, light, name_size, ink)
        pen.text("Varas", x, y, bold, name_size, ink)
        y -= 16
        y = pen.para(str(cv.get("title", "")), main_x, y, main_w, semibold, 9.6, 12.0, accent)
        y -= 8 * s

        def skills(y: float) -> float:
            groups = cv.get("skills", [])
            if not groups:
                return y
            y = heading(pen, str(cv.get("skills_title") or "Compétences"), main_x, y, main_w, s)
            col_gap = 6 * mm
            col_w = (main_w - col_gap) / 2
            for row in range(0, len(groups), 2):
                row_bottom = y
                for col, group in enumerate(groups[row:row + 2]):
                    gx = main_x + col * (col_w + col_gap)
                    gy = pen.para(str(group.get("title", "")), gx, y, col_w, bold, 8.2 * s, 10.4 * s, ink)
                    items = " · ".join(str(i) for i in group.get("items", []))
                    gy = pen.para(items, gx, gy - 0.6 * s, col_w, regular, small, small_lead, soft)
                    row_bottom = min(row_bottom, gy)
                y = row_bottom - 3.4 * s
            return y - 4 * s

        def experiences(y: float) -> float:
            exps = cv.get("experiences", [])
            if not exps:
                return y
            y = heading(pen, "Expériences", main_x, y, main_w, s)
            bx = main_x + 3.6 * mm
            bw = main_right - bx
            for exp in exps:
                top_y = y + 9.4 * s
                period = str(exp.get("period", ""))
                pw = stringWidth(period, semibold, small)
                title_w = bw - pw - 8
                ty = pen.para(str(exp.get("title", "")), bx, y, title_w, bold, 9.2 * s, 11.2 * s, ink)
                pen.text(period, main_right - pw, y, semibold, small, accent)
                y = ty - 0.6 * s
                # Organisation puis liens cliquables, sur la même ligne si possible.
                org = str(exp.get("organization", ""))
                links = [str(link) for link in exp.get("links", [])[:2]]
                segments: List[Tuple[str, Any, str | None]] = [(org, soft, None)] if org else []
                for link in links:
                    segments.append((_display_url(link), accent, _href(link)))
                cx, line_y = bx, y
                for index, (label, color, url) in enumerate(segments):
                    piece = label if index == 0 else f" · {label}"
                    pw_ = stringWidth(piece, regular, small)
                    if cx > bx and cx + pw_ > main_right:
                        line_y -= small_lead
                        cx = bx
                        piece = label
                        pw_ = stringWidth(piece, regular, small)
                    if pw_ > main_right - bx:  # organisation très longue
                        line_y = pen.para(piece, bx, line_y, bw, regular, small, small_lead, color, url) + small_lead
                        cx = bx + stringWidth(wrap(piece, bw, regular, small)[-1], regular, small)
                        continue
                    if index and piece.startswith(" · "):
                        sep_w = pen.text(" · ", cx, line_y, regular, small, soft)
                        pen.text(label, cx + sep_w, line_y, regular, small, color, url)
                    else:
                        pen.text(piece, cx, line_y, regular, small, color, url)
                    cx += pw_
                y = (line_y - small_lead) if segments else y
                y -= 1.0 * s
                for bullet in exp.get("bullets", [])[:3]:
                    lines = wrap(str(bullet), bw - 3.6 * mm, regular, body)
                    if pen.draw and lines:
                        c.setFillColor(accent)
                        c.circle(bx + 1.6 * mm, y + body * 0.33, 1.05, stroke=0, fill=1)
                    for ln in lines:
                        pen.text(ln, bx + 3.6 * mm, y, regular, body, body_c)
                        y -= lead
                    y -= 0.9 * s
                pen.vline(main_x + 0.6, top_y, y + lead * 0.55, line_c)
                y -= 6.0 * s
            return y

        def projects(y: float) -> float:
            items = cv.get("projects", [])[:2]
            if not items:
                return y
            y = heading(pen, "Projets personnels" if len(items) > 1 else "Projet personnel", main_x, y, main_w, s)
            for project in items:
                name, sub = _split_title(str(project.get("title", "")))
                x = main_x
                x += pen.text(name, x, y, bold, 9.0 * s, ink)
                if sub:
                    rest = f" — {sub}"
                    if x + stringWidth(rest, regular, 8.6 * s) <= main_right:
                        pen.text(rest, x, y, regular, 8.6 * s, soft)
                    else:
                        y -= 11 * s
                        y = pen.para(sub, main_x, y, main_w, regular, 8.6 * s, 11 * s, soft) + 11 * s
                y -= 11 * s
                y = pen.para(str(project.get("description", "")), main_x, y, main_w, regular, body, lead, body_c)
                tech = ", ".join(str(t) for t in project.get("technologies", []))
                links = [str(link) for link in project.get("links", [])[:2]]
                cx = main_x
                if tech:
                    cx += pen.text(tech, cx, y, regular, small, soft)
                for link in links:
                    sep = " · " if cx > main_x else ""
                    label = _display_url(link)
                    if cx + stringWidth(sep + label, regular, small) > main_right:
                        y -= small_lead
                        cx, sep = main_x, ""
                    cx += pen.text(sep, cx, y, regular, small, soft)
                    cx += pen.text(label, cx, y, regular, small, accent, _href(link))
                if tech or links:
                    y -= small_lead
                y -= 5.0 * s
            return y - 2 * s

        def education(y: float) -> float:
            items = cv.get("education", [])
            if not items:
                return y
            y = heading(pen, "Formation", main_x, y, main_w, s)
            year_w = 10.5 * mm * s
            for edu in items:
                year, title, extra = _education_parts(edu)
                pen.text(year, main_x, y, semibold, body, accent)
                x = main_x + year_w
                text_w = main_right - x
                head = title
                tail = f" — {extra}" if extra else ""
                if stringWidth(head + tail, bold, body) <= text_w:
                    x += pen.text(head, x, y, semibold, body, ink)
                    if tail:
                        pen.text(tail, x, y, regular, body, soft)
                    y -= lead
                else:
                    y = pen.para(head + tail, x, y, text_w, semibold, body, lead, ink)
                y -= 1.2 * s
            return y

        drawers: Dict[str, Callable[[float], float]] = {
            "skills": skills, "experiences": experiences, "projects": projects, "education": education,
        }
        order = [n for n in cv.get("section_order", []) if n in drawers]
        order += [n for n in drawers if n not in order]
        for name in order:
            y = drawers[name](y)
        return y

    # ---------------------------------------------------------- colonne gauche
    online = _online_work(cv)
    flag = cv.get("show_online_work")
    digital_profile = str(final_cv.get("base_variant") or "") not in NON_DIGITAL_VARIANTS
    want_online = bool(online) and (flag is True or (flag is None and digital_profile and len(online) >= 2))

    def side_column(pen: Pen, with_online: bool) -> float:
        body, lead = 8.2, 11.2
        diameter = 36 * mm
        px = (side_w - diameter) / 2
        py = height - 13 * mm - diameter
        if pen.draw:
            portrait = Path(portrait_path)
            c.setFillColor(colors.white)
            c.circle(px + diameter / 2, py + diameter / 2, diameter / 2 + 2.6, stroke=0, fill=1)
            if portrait.exists():
                image = ImageReader(str(portrait))
                iw, ih = image.getSize()
                f = max(diameter / iw, diameter / ih)
                dw, dh = iw * f, ih * f
                c.saveState()
                clip = c.beginPath()
                clip.circle(px + diameter / 2, py + diameter / 2, diameter / 2)
                c.clipPath(clip, stroke=0, fill=0)
                c.drawImage(image, px - (dw - diameter) / 2, py - (dh - diameter) / 2, width=dw, height=dh, mask="auto")
                c.restoreState()
            else:
                c.setFillColor(line_c)
                c.circle(px + diameter / 2, py + diameter / 2, diameter / 2, stroke=0, fill=1)
        y = py - 9 * mm
        if cv.get("profile"):
            y = heading(pen, "Profil", side_x, y, side_inner, 1.0)
            y = pen.para(str(cv["profile"]), side_x, y, side_inner, regular, body, lead, ink) - 5 * mm
        rows = [
            (contact.get("email"), "email"), (contact.get("phone"), "tel"),
            (cv.get("location"), None), (contact.get("portfolio"), "web"), (contact.get("github"), "web"),
        ]
        rows = [(v, k) for v, k in rows if v]
        if rows:
            y = heading(pen, "Contact", side_x, y, side_inner, 1.0)
            for value, kind in rows:
                label = _display_url(value) if kind == "web" else str(value)
                color = accent if kind else ink
                y = pen.para(label, side_x, y, side_inner, regular, 8.0, 10.6, color, _href(value, kind) if kind else None)
                y -= 2.4
            y -= 4 * mm
        if with_online:
            y = heading(pen, "Réalisations en ligne", side_x, y, side_inner, 1.0)
            for label, url in online:
                y = pen.para(label, side_x, y, side_inner, regular, 8.0, 10.6, accent, _href(url)) - 2.4
            y -= 4 * mm
        if cv.get("languages"):
            y = heading(pen, "Langues", side_x, y, side_inner, 1.0)
            for lang in cv["languages"]:
                name = str(lang.get("name", ""))
                level = str(lang.get("level", ""))
                x = side_x + pen.text(name, side_x, y, semibold, 8.0, ink)
                if level:
                    pen.text(f" — {level}", x, y, regular, 8.0, soft)
                y -= 11.0
        return y

    if want_online and side_column(Pen(False), True) < page_bottom:
        want_online = False  # la colonne gauche ne tiendrait pas : on retire la rubrique facultative

    # Un CV court s'agrandit un peu au lieu de laisser le bas de page vide ;
    # un CV dense se resserre jusqu'à tenir sur une page.
    scale = 0.78
    for candidate in (1.12, 1.08, 1.04, 1.0, 0.97, 0.94, 0.91, 0.88, 0.85, 0.82, 0.8, 0.78):
        if main_column(Pen(False), candidate) >= page_bottom:
            scale = candidate
            break

    c.setFillColor(tint)
    c.rect(0, 0, side_w, height, stroke=0, fill=1)
    side_column(Pen(True), want_online)
    main_column(Pen(True), scale)
    c.showPage()
    c.save()
