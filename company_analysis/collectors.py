"""Collecteurs de faits bruts sur une entreprise.

Déterministes, sans IA. Chaque collecteur retourne strictement le même contrat :

    {"tool", "url", "value", "evidence", "measured_at", "error"}

`evidence` n'est jamais vide quand `error` vaut None : c'est la citation, l'en-tête
HTTP ou l'extrait de page qui atteste la valeur. C'est ce champ qui rend le
Vérificateur possible — sans lui, rien ne peut être confirmé.

Tout texte lu sur un site est une donnée non fiable. Ces fonctions le recopient
comme preuve, elles ne l'interprètent pas et ne lui obéissent jamais.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = "job-search-automation/1.0 (prospection; +https://varascundo.com)"
REQUEST_TIMEOUT_SECONDS = 15
MAX_RESPONSE_BYTES = 2_000_000
MAX_PAGES_PER_COMPANY = 4
MAX_EVIDENCE_CHARS = 300

CAREERS_HINTS = (
    "recrutement",
    "recrute",
    "carriere",
    "carrieres",
    "nous-rejoindre",
    "rejoignez",
    "rejoindre",
    "jobs",
    "job",
    "careers",
    "offres-emploi",
    "offre-emploi",
    "emploi",
    "talents",
)
CONTACT_HINTS = ("contact", "mentions-legales", "mentions_legales", "mentionslegales", "legal")

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

GENERIC_EMAIL_PREFIXES = (
    "contact",
    "bonjour",
    "hello",
    "info",
    "infos",
    "recrutement",
    "job",
    "jobs",
    "candidature",
    "rh",
    "accueil",
)

# Les signatures en mot simple sont bornées par \b. Sans cela, le nom de la
# technologie se retrouve dans un identifiant plus long qui ne la concerne pas :
# `elementorySupportWixCodeSdk` est un SDK Wix, et faisait conclure « Elementor ».
STACK_SIGNATURES = (
    ("WordPress", re.compile(r"wp-content|wp-includes|wp-json", re.I)),
    ("Elementor", re.compile(r"\belementor\b", re.I)),
    ("WooCommerce", re.compile(r"\bwoocommerce\b", re.I)),
    ("Drupal", re.compile(r"\bdrupal\b", re.I)),
    ("Joomla", re.compile(r"\bjoomla\b", re.I)),
    ("Next.js", re.compile(r"__NEXT_DATA__|/_next/", re.I)),
    ("Nuxt", re.compile(r"__NUXT__|/_nuxt/", re.I)),
    ("Webflow", re.compile(r"\bwebflow\b", re.I)),
    ("Wix", re.compile(r"wix\.com|wixstatic", re.I)),
    ("Squarespace", re.compile(r"\bsquarespace\b", re.I)),
    ("Shopify", re.compile(r"\bshopify\b", re.I)),
    ("Symfony", re.compile(r"\bsymfony\b", re.I)),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _measurement(
    tool: str,
    url: str,
    value: Dict[str, Any] | None = None,
    evidence: str = "",
    error: str | None = None,
) -> Dict[str, Any]:
    """Construit le contrat commun. Une mesure sans preuve est une erreur."""
    if error is None and not str(evidence).strip():
        error = "preuve absente : mesure inexploitable"
    return {
        "tool": tool,
        "url": url,
        "value": value or {},
        "evidence": _clip(evidence) if error is None else "",
        "measured_at": _now(),
        "error": error,
    }


def _clip(text: str, limit: int = MAX_EVIDENCE_CHARS) -> str:
    flattened = re.sub(r"\s+", " ", str(text)).strip()
    return flattened if len(flattened) <= limit else flattened[: limit - 1] + "…"


def _fetch(url: str) -> requests.Response:
    """GET plafonné. Aucun formulaire soumis, aucun script exécuté."""
    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        allow_redirects=True,
        stream=True,
    )
    body = response.raw.read(MAX_RESPONSE_BYTES, decode_content=True) or b""
    response._content = body  # noqa: SLF001 - plafonne la taille lue
    return response


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def normalize_domain(url: str) -> Dict[str, Any]:
    """Normalise le domaine pour empêcher les doublons."""
    raw = str(url or "").strip()
    if not raw:
        return _measurement("normalize_domain", raw, error="URL vide")
    candidate = raw if "://" in raw else f"https://{raw}"
    host = (urlparse(candidate).hostname or "").lower()
    if not host:
        return _measurement("normalize_domain", raw, error=f"URL illisible : {raw}")
    domain = host[4:] if host.startswith("www.") else host
    return _measurement(
        "normalize_domain",
        raw,
        value={"domain": domain, "host": host},
        evidence=f"URL fournie : {raw}",
    )


def check_http(url: str) -> Dict[str, Any]:
    """Code HTTP, redirections, HTTPS et temps de réponse."""
    try:
        response = _fetch(url)
    except requests.RequestException as exc:
        return _measurement("check_http", url, error=f"{type(exc).__name__}: {exc}")

    redirects = [step.headers.get("Location", step.url) for step in response.history]
    final_url = response.url
    return _measurement(
        "check_http",
        url,
        value={
            "status_code": response.status_code,
            "final_url": final_url,
            "https": final_url.lower().startswith("https://"),
            "redirects": redirects,
            "redirect_count": len(response.history),
            "elapsed_seconds": round(response.elapsed.total_seconds(), 3),
            "content_type": response.headers.get("Content-Type", ""),
        },
        evidence=(
            f"HTTP {response.status_code} sur {final_url} "
            f"(content-type: {response.headers.get('Content-Type', 'non renseigné')}, "
            f"{len(response.history)} redirection(s), "
            f"{round(response.elapsed.total_seconds(), 3)}s)"
        ),
    )


def inspect_metadata(url: str) -> Dict[str, Any]:
    """Title, meta description, langue déclarée et principaux headings."""
    try:
        response = _fetch(url)
        response.raise_for_status()
    except requests.RequestException as exc:
        return _measurement("inspect_metadata", url, error=f"{type(exc).__name__}: {exc}")

    soup = _soup(response.text)
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    description_tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    description = str(description_tag.get("content") or "").strip() if description_tag else ""
    html_tag = soup.find("html")
    language = str(html_tag.get("lang") or "").strip() if html_tag else ""
    headings = [
        _clip(tag.get_text(" ", strip=True), 120)
        for tag in soup.find_all(["h1", "h2"])[:8]
        if tag.get_text(strip=True)
    ]

    if not any([title, description, language, headings]):
        return _measurement(
            "inspect_metadata",
            url,
            error="aucune métadonnée lisible dans la page",
        )

    return _measurement(
        "inspect_metadata",
        url,
        value={
            "title": title,
            "description": description,
            "language": language,
            "headings": headings,
        },
        evidence=(
            f"<title>{title or 'absent'}</title> | lang={language or 'absent'} | "
            f"description={description or 'absente'} | h1/h2: {'; '.join(headings) or 'aucun'}"
        ),
    )


def detect_stack(url: str) -> Dict[str, Any]:
    """Générateur, framework ou CMS visibles dans le HTML servi."""
    try:
        response = _fetch(url)
        response.raise_for_status()
    except requests.RequestException as exc:
        return _measurement("detect_stack", url, error=f"{type(exc).__name__}: {exc}")

    html = response.text
    soup = _soup(html)
    generator_tag = soup.find("meta", attrs={"name": re.compile(r"^generator$", re.I)})
    generator = str(generator_tag.get("content") or "").strip() if generator_tag else ""

    detected: List[str] = []
    proofs: List[str] = []
    for name, pattern in STACK_SIGNATURES:
        match = pattern.search(html)
        if match:
            detected.append(name)
            start = max(0, match.start() - 40)
            proofs.append(f"{name} ← « {_clip(html[start : match.end() + 40], 100)} »")

    if not generator and not detected:
        # Rien de visible n'est un fait négatif utile, mais il reste prouvé par
        # la lecture de la page : on l'atteste par la taille lue.
        return _measurement(
            "detect_stack",
            url,
            value={"generator": "", "detected": [], "powered_by": response.headers.get("X-Powered-By", "")},
            evidence=f"Aucune signature de CMS ou framework dans les {len(html)} caractères servis par {response.url}",
        )

    return _measurement(
        "detect_stack",
        url,
        value={
            "generator": generator,
            "detected": detected,
            "powered_by": response.headers.get("X-Powered-By", ""),
        },
        evidence=" | ".join(
            part for part in ([f"<meta generator> : {generator}"] if generator else []) + proofs
        ),
    )


def _internal_links(base_url: str, html: str, hints: tuple[str, ...]) -> List[tuple[str, str]]:
    """Liens internes dont l'URL ou le libellé évoque l'un des indices."""
    soup = _soup(html)
    base_host = (urlparse(base_url).hostname or "").lower().removeprefix("www.")
    found: List[tuple[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = urljoin(base_url, href)
        host = (urlparse(absolute).hostname or "").lower().removeprefix("www.")
        if host != base_host:
            continue
        label = anchor.get_text(" ", strip=True)
        haystack = f"{absolute} {label}".lower()
        if any(hint in haystack for hint in hints) and absolute not in seen:
            seen.add(absolute)
            found.append((absolute, label))
    return found


def find_careers_signals(url: str) -> Dict[str, Any]:
    """Page carrières et mentions de recrutement visibles depuis l'accueil."""
    try:
        response = _fetch(url)
        response.raise_for_status()
    except requests.RequestException as exc:
        return _measurement("find_careers_signals", url, error=f"{type(exc).__name__}: {exc}")

    links = _internal_links(response.url, response.text, CAREERS_HINTS)[:MAX_PAGES_PER_COMPANY]
    if not links:
        return _measurement(
            "find_careers_signals",
            url,
            value={"has_careers_page": False, "pages": [], "mentions": []},
            evidence=f"Aucun lien interne évoquant le recrutement parmi les liens de {response.url}",
        )

    pages: List[Dict[str, Any]] = []
    mentions: List[str] = []
    for link_url, label in links:
        entry: Dict[str, Any] = {"url": link_url, "label": label, "status_code": None}
        try:
            page = _fetch(link_url)
            entry["status_code"] = page.status_code
            if page.ok:
                text = _soup(page.text).get_text(" ", strip=True)
                for hint in ("recrut", "rejoign", "candidat", "poste", "stage", "alternance"):
                    match = re.search(rf"[^.]*{hint}[^.]*\.", text, re.I)
                    if match:
                        mentions.append(f"{link_url} : « {_clip(match.group(0), 160)} »")
                        break
        except requests.RequestException as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
        pages.append(entry)

    return _measurement(
        "find_careers_signals",
        url,
        value={"has_careers_page": True, "pages": pages, "mentions": mentions},
        evidence=" | ".join(
            [f"Lien « {label or 'sans libellé'} » vers {link_url}" for link_url, label in links]
            + mentions
        ),
    )


def extract_public_contact(url: str) -> Dict[str, Any]:
    """Adresse professionnelle publiquement affichée, avec sa source."""
    try:
        response = _fetch(url)
        response.raise_for_status()
    except requests.RequestException as exc:
        return _measurement("extract_public_contact", url, error=f"{type(exc).__name__}: {exc}")

    candidates: List[tuple[str, str]] = [(response.url, response.text)]
    for link_url, _ in _internal_links(response.url, response.text, CONTACT_HINTS)[:2]:
        try:
            page = _fetch(link_url)
            if page.ok:
                candidates.append((page.url, page.text))
        except requests.RequestException:
            continue

    emails: List[Dict[str, str]] = []
    seen: set[str] = set()
    for source_url, html in candidates:
        for raw_email in EMAIL_PATTERN.findall(html):
            email = raw_email.lower().strip(".")
            if email in seen or email.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
                continue
            seen.add(email)
            emails.append({"email": email, "source": source_url})

    if not emails:
        return _measurement(
            "extract_public_contact",
            url,
            value={"emails": [], "generic_emails": []},
            evidence=f"Aucune adresse email affichée sur {', '.join(page_url for page_url, _ in candidates)}",
        )

    generic = [
        item["email"]
        for item in emails
        if item["email"].split("@", 1)[0] in GENERIC_EMAIL_PREFIXES
    ]
    return _measurement(
        "extract_public_contact",
        url,
        value={"emails": emails, "generic_emails": generic},
        evidence=" | ".join(f"{item['email']} affichée sur {item['source']}" for item in emails[:5]),
    )


COLLECTORS = {
    "check_http": check_http,
    "inspect_metadata": inspect_metadata,
    "detect_stack": detect_stack,
    "find_careers_signals": find_careers_signals,
    "extract_public_contact": extract_public_contact,
    "normalize_domain": normalize_domain,
}
