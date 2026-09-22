"""Tests du décodeur Cloudflare cfemail (utils/email_protection.py)."""

from utils.email_protection import decode_cfemail, decode_protected_emails


def _encode(addr: str, key: int = 0x1F) -> str:
    """Encode selon la spécification Cloudflare : clé XOR en tête, puis octets chiffrés."""
    return f"{key:02x}" + "".join(f"{ord(c) ^ key:02x}" for c in addr)


def test_decode_cfemail_roundtrip():
    hexcode = _encode("contact@example.com")
    assert decode_cfemail(hexcode) == "contact@example.com"


def test_decode_cfemail_rejects_malformed_payloads():
    assert decode_cfemail("") is None
    assert decode_cfemail("zz") is None
    assert decode_cfemail("1f") is None          # clé sans charge utile
    assert decode_cfemail("1f4") is None         # longueur impaire
    assert decode_cfemail("1f4142zz") is None    # hexadécimal invalide
    # un décodage valide mais non-email est renvoyé tel quel : le filtre
    # EMAIL_RE de decode_protected_emails l'écarte ensuite.
    assert decode_cfemail("1f41") == "^"


def test_decode_protected_emails_finds_cfemail_and_mailto():
    html = (
        '<a href="/cdn-cgi/l/email-protection#' + _encode("agence@yotta.paris") + '">'
        '<span class="__cf_email__" data-cfemail="' + _encode("candidature@yotta.paris") + '"></span>'
        '<a href="mailto:Hello%40Site-Easy.fr?subject=Contact">écrire</a>'
    )
    assert decode_protected_emails(html) == [
        "agence@yotta.paris",
        "candidature@yotta.paris",
        "hello@site-easy.fr",
    ]


def test_decode_protected_emails_ignores_plaintext_and_garbage():
    html = '<p>contact@clair.fr</p><span data-cfemail="12345678"></span>'
    # le clair est volontairement ignoré (l'appelant a son extraction) ;
    # le payload invalide ne produit rien et ne lève jamais.
    assert decode_protected_emails(html) == []
    assert decode_protected_emails("") == []
    assert decode_protected_emails(None) == []
