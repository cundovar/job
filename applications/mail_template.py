"""Rendu HTML des mails de candidature depuis le gabarit de Cundo.

Le gabarit (applications/templates/mail_candidature.html) est SA source de
vérité visuelle : il peut l'éditer directement, le rendu s'adapte. Le corps
texte du dossier (mail_candidature.md, éditable par lui) est découpé en zones
— salutation, paragraphes, ligne « CV joint », clôture, formule — et injecté
dans le gabarit. Ce qui n'est pas reconnu reste dans les paragraphes : une
édition libre ne perd jamais de texte.
"""
from __future__ import annotations

import re
from html import escape
from pathlib import Path

from jinja2 import Environment

TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "mail_candidature.html"

_FORMULE_RE = re.compile(
    r"^(Cordialement|Bien à vous|Bien cordialement|Sincèrement|Respectueusement)\s*,?\s*$",
    re.I,
)
_SIGNATURE_RE = re.compile(r"^Facundo Varas(\s*\(Cundo\))?\s*$", re.I)
_CLOTURE_RE = re.compile(r"disposition|échange|ravirai de vous", re.I)
_SALUTATION_RE = re.compile(r"^(Bonjour|Madame, Monsieur|Messieurs|Chère? )[\s,ÀÉÈa-zà-ÿ'-]{0,30}$", re.I)


def parse_mail_body(body: str) -> dict:
    """Découpe le corps texte édité en zones du gabarit.

    Tout ce qui n'est ni salutation, ni ligne « CV joint », ni « Portfolio »,
    ni formule de politesse, ni signature reste un paragraphe — une édition
    libre ne perd jamais de texte.
    """
    salutation = None
    cv_intitule = None
    portfolio_url = None
    portfolio_label = None
    formule = None
    cloture = None
    paragraphes: list[str] = []
    current: list[str] = []
    seen_body = False

    def flush():
        if current:
            paragraphes.append(escape(" ".join(current)))
            current.clear()

    blocks = [block.strip() for block in (body or "").split("\n\n") if block.strip()]
    for index, block in enumerate(blocks):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        # Salutation : premier bloc, court, forme d'interpellation.
        if salutation is None and index == 0 and len(block) <= 40 and _SALUTATION_RE.match(block):
            salutation = block
            continue
        for line in lines:
            low = line.lower()
            if low.startswith("cv joint"):
                cv_intitule = escape(line.split(":", 1)[1].strip() if ":" in line else line)
                continue
            if low.startswith("portfolio"):
                found = re.search(r"(https?://\S+|[\w.-]+\.[a-z]{2,}[/\w.-]*)", line)
                if found:
                    url = found.group(0)
                    portfolio_url = url if url.startswith("http") else "https://" + url
                    portfolio_label = portfolio_url.split("://", 1)[1].strip("/")
                continue
            if _FORMULE_RE.match(line):
                formule = line
                continue
            if _SIGNATURE_RE.match(line):
                continue
            current.append(line)
        flush()

    if paragraphes:
        last = paragraphes[-1]
        plain = re.sub(r"<[^>]+>", "", last)
        if _CLOTURE_RE.search(plain) and len(plain) < 140:
            cloture = last
            paragraphes.pop()
    return {
        "salutation": escape(salutation) if salutation else None,
        "paragraphes": paragraphes,
        "cv_intitule": cv_intitule,
        "portfolio_url": portfolio_url,
        "portfolio_label": portfolio_label,
        "cloture": cloture,
        "formule": formule,
    }


def render_mail_html(subject: str, body: str, sender_email: str,
                     candidate_name: str = "Facundo Varas",
                     candidate_titre: str = "Développeur web &amp; formateur — Paris") -> str:
    """Rend le corps texte édité dans le gabarit HTML de Cundo."""
    zones = parse_mail_body(body)
    context = {
        "objet": subject,
        "expediteur_nom": escape(candidate_name),
        "expediteur_titre": candidate_titre,
        "email": escape(sender_email),
        "salutation": zones["salutation"],
        "paragraphes": zones["paragraphes"],
        "cv_intitule": zones["cv_intitule"],
        "portfolio_url": zones["portfolio_url"],
        "portfolio_label": zones["portfolio_label"],
        "cloture": zones["cloture"],
        "formule": zones["formule"],
        "github_url": None,
    }
    environment = Environment(autoescape=False)
    return environment.from_string(TEMPLATE_PATH.read_text(encoding="utf-8")).render(**context)
