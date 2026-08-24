from __future__ import annotations

from html import escape
from typing import Any, Dict, List


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


def cv_to_html(final_cv: Dict[str, Any]) -> str:
    cv = final_cv.get("cv", {})
    md = cv_to_markdown(final_cv)
    body_lines = []
    for line in md.splitlines():
        if line.startswith("# "):
            body_lines.append(f"<h1>{escape(line[2:])}</h1>")
        elif line.startswith("## "):
            body_lines.append(f"<h2>{escape(line[3:])}</h2>")
        elif line.startswith("### "):
            body_lines.append(f"<h3>{escape(line[4:])}</h3>")
        elif line.startswith("- "):
            body_lines.append(f"<p class='bullet'>• {escape(line[2:])}</p>")
        elif line.strip():
            body_lines.append(f"<p>{escape(line)}</p>")
        else:
            body_lines.append("")
    return """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>CV personnalisé - Facundo Varas</title>
<style>
  body { font-family: Arial, sans-serif; color: #1F2933; margin: 36px; line-height: 1.35; }
  h1 { margin-bottom: 0; font-size: 28px; }
  h2 { color: #0F766E; border-bottom: 1px solid #D7E5E3; padding-bottom: 3px; font-size: 15px; margin-top: 18px; }
  h3 { font-size: 12px; margin-bottom: 2px; }
  p { font-size: 10px; margin: 4px 0; }
  .bullet { margin-left: 12px; }
</style>
</head>
<body>
""" + "\n".join(body_lines) + "\n</body>\n</html>\n"
