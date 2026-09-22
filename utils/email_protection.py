"""Décodage des emails masqués par la protection anti-spam Cloudflare.

Le format ``data-cfemail="HEX"`` (et les liens ``/cdn-cgi/l/email-protection#HEX``)
encode l'adresse ainsi : le premier octet hexadécimal est la clé XOR, chaque
octet suivant est un caractère chiffré. Le décodage est déterministe et
hors ligne — aucun navigateur ni rendu JavaScript nécessaire.

Une adresse encodée est une adresse que le site a volontairement publiée :
la décoder revient à lire le pied de page, pas à contourner une intention.
"""
from __future__ import annotations

import re
from urllib.parse import unquote

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

_CFEMAIL_HEX = re.compile(r'data-cfemail="([0-9a-fA-F]+)"')
_CFEMAIL_LINK = re.compile(r"email-protection#([0-9a-fA-F]+)")
_MAILTO = re.compile(r"mailto:([^\"'>\s\\]+)", re.I)


def decode_cfemail(encoded: str) -> str | None:
    """Décode une charge utile cfemail hexadécimale. Renvoie None si malformée."""
    encoded = (encoded or "").strip()
    if len(encoded) < 4 or len(encoded) % 2 != 0 or not re.fullmatch(r"[0-9a-fA-F]+", encoded):
        return None
    key = int(encoded[:2], 16)
    try:
        decoded = "".join(
            chr(int(encoded[i:i + 2], 16) ^ key) for i in range(2, len(encoded), 2)
        )
    except ValueError:
        return None
    return decoded or None


def decode_protected_emails(html: str | None) -> list[str]:
    """Emails *masqués* trouvés dans un HTML brut : cfemail décodés + mailto.

    Les adresses en clair ne sont pas retournées ici : les appelants ont déjà
    leur propre extraction par regex sur le HTML ou le texte.
    """
    if not html:
        return []
    found: set[str] = set()
    for hexcode in _CFEMAIL_HEX.findall(html) + _CFEMAIL_LINK.findall(html):
        decoded = decode_cfemail(hexcode)
        if decoded and EMAIL_RE.fullmatch(decoded):
            found.add(decoded.lower())
    for target in _MAILTO.findall(html):
        addr = unquote(target).split("?", 1)[0].strip(".")
        if EMAIL_RE.fullmatch(addr):
            found.add(addr.lower())
    return sorted(found)
