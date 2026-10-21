"""docdevdoc.varascundo.com ne figure plus sur aucun CV ; /docs/ le remplace."""
from cv_generator import rules
from cv_generator.cv_pdf_design import _online_work


def test_lien_retire_reconnu_quelle_que_soit_la_forme():
    assert rules.is_retired_link("https://docdevdoc.varascundo.com")
    assert rules.is_retired_link("https://www.docdevdoc.varascundo.com/page")
    assert rules.is_retired_link("docdevdoc.varascundo.com")
    assert not rules.is_retired_link("https://devdoc.varascundo.com/docs/")


def test_shown_links_retire_et_dedoublonne():
    links = ["https://devdoc.varascundo.com", "https://docdevdoc.varascundo.com", "https://devdoc.varascundo.com"]
    assert rules.shown_links(links) == ["https://devdoc.varascundo.com"]


def _cv(**extra):
    cv = {
        "experiences": [
            {"organization": "Éditions Chant d'orties", "links": ["https://tuto-des-orties.varascundo.com/"]},
            {
                "organization": "Pôle S",
                "links": [
                    "https://devdoc.varascundo.com",
                    "https://docdevdoc.varascundo.com",
                    "https://devdoc.varascundo.com/docs/",
                ],
            },
        ],
        "projects": [
            {
                "title": "DevDoc — plateforme",
                "links": ["https://devdoc.varascundo.com/", "https://devdoc.varascundo.com/docs/"],
            },
            {"title": "La Magicieuse — site", "links": ["https://la-magicieuse.org"]},
        ],
    }
    cv.update(extra)
    return cv


def test_realisations_en_ligne_sans_docdevdoc_avec_docs():
    urls = [url for _label, url in _online_work(_cv())]
    assert not any("docdevdoc" in url for url in urls)
    labels = [label for label, _url in _online_work(_cv())]
    assert labels == [
        "Chant d'Orties — guide",
        "devdoc.varascundo.com",
        "devdoc.varascundo.com/docs",
        "La Magicieuse",
    ]


def test_selection_manuelle_ne_reintroduit_pas_un_lien_retire():
    override = [
        {"label": "doc", "url": "https://docdevdoc.varascundo.com"},
        {"label": "docs", "url": "https://devdoc.varascundo.com/docs/"},
    ]
    assert _online_work(_cv(online_work=override)) == [("docs", "https://devdoc.varascundo.com/docs/")]
