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


# ── Mise en page : découpage en parties d'une lettre française ───────────

from cv_generator.exporters import _lettre_inline, _parse_lettre_structure

LETTRE_COMPLETE = """# Lettre de motivation

Paris, le 28 septembre 2026

Ville de Montreuil
Direction de la communication

Objet : Candidature au poste de Webmaster

Madame, Monsieur,

Je gère des sites **WordPress** depuis 2023,
et je documente ce que je livre.

Je serais heureux d'échanger avec vous.

Cordialement,

Facundo Varas
Portfolio : varascundo.com
"""


def test_structure_reconnait_chaque_partie_sans_rien_reecrire():
    parts = _parse_lettre_structure(LETTRE_COMPLETE)
    assert parts["date"] == "Paris, le 28 septembre 2026"
    assert parts["recipient"] == ["Ville de Montreuil", "Direction de la communication"]
    assert parts["objet"] == "Objet : Candidature au poste de Webmaster"
    assert parts["salutation"] == "Madame, Monsieur,"
    assert parts["body"] == [
        "Je gère des sites **WordPress** depuis 2023, et je documente ce que je livre.",
        "Je serais heureux d'échanger avec vous.",
    ]
    assert parts["closing"] == ["Cordialement,"]
    assert parts["signature"] == ["Facundo Varas", "Portfolio : varascundo.com"]


def test_sans_objet_rien_nest_pris_pour_un_destinataire():
    parts = _parse_lettre_structure("Bonjour,\n\nTexte de la lettre.\n\nCordialement,\n\nFacundo Varas\n")
    assert parts["recipient"] == []
    assert parts["salutation"] == "Bonjour,"
    assert parts["body"] == ["Texte de la lettre."]
    assert parts["signature"] == ["Facundo Varas"]


def test_le_markdown_en_ligne_devient_du_gras_et_reste_echappe():
    assert _lettre_inline("un **mot** & <b>") == "un <b>mot</b> &amp; &lt;b&gt;"
    assert _lettre_inline("voir [le site](https://x.fr)") == "voir le site"


def test_une_lettre_complete_tient_sur_une_page(tmp_path):
    md = tmp_path / "lettre_motivation.md"
    md.write_text(LETTRE_COMPLETE, encoding="utf-8")
    pdf = tmp_path / "lettre_motivation.pdf"
    lettre_to_pdf(md, pdf)
    from pypdf import PdfReader

    assert len(PdfReader(str(pdf)).pages) == 1
