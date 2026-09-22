"""Tests de l'export PDF de la lettre de motivation (cv_generator/exporters.py)."""

from cv_generator.exporters import _parse_lettre_markdown, lettre_to_pdf

LETTRE = """Objet : Candidature spontanée — Développeur web

Bonjour,

Je vous adresse une candidature spontanée au sein de votre agence.
Développeur web depuis 2023, je travaille en PHP/Symfony et WordPress.

Pour un poste au sein de votre équipe comme pour un renfort ponctuel,
je reste disponible pour un échange.

Cordialement,

Facundo Varas
"""


def test_parse_extracts_objet_and_paragraphs():
    date_line, objet, paragraphs = _parse_lettre_markdown(LETTRE)
    assert date_line == ""
    assert objet.startswith("Objet : Candidature spontanée")
    assert paragraphs[0] == "Bonjour,"
    assert any("2023" in p for p in paragraphs)
    assert paragraphs[-1] == "Facundo Varas"


def test_parse_extracts_the_place_and_date_line():
    date_line, objet, _ = _parse_lettre_markdown(
        "Paris, le 22 septembre 2026\n\nObjet : Candidature\n\nBonjour,\n\nTexte.\n"
    )
    assert date_line == "Paris, le 22 septembre 2026"
    assert objet == "Objet : Candidature"


def test_lettre_to_pdf_produces_a_valid_document(tmp_path):
    md = tmp_path / "lettre_motivation.md"
    md.write_text(LETTRE, encoding="utf-8")
    pdf = tmp_path / "lettre_motivation.pdf"

    lettre_to_pdf(md, pdf)

    assert pdf.exists()
    head = pdf.read_bytes()[:5]
    assert head == b"%PDF-"
