#!/usr/bin/env python3
"""Trouver le site officiel d'une structure du registre — ou n'en trouver aucun.

Pourquoi ce module existe
-------------------------

Le registre public publie une raison sociale, un SIREN et un siège. Il ne publie
**pas de site**. Or sans site il n'y a pas d'auto-description, donc pas de
verdict d'activité : le candidat restait `incertain`, `score: 0`, et finissait
soit affiché comme « Agence 0/100 » — KONEXIO, organisme de formation, en est
l'exemple —, soit masqué par le filtre de publication. Dans les deux cas
l'annuaire ne produisait que du bruit.

Ce module comble l'étape manquante :

    registre → recherche du site officiel → vérification d'identité → crawl → score

et jamais `registre → affichage direct`.

La règle qui ne se négocie pas
------------------------------

**Sans preuve, on ignore.** Aucun domaine n'est déduit d'un nom : `KONEXIO` ne
devient pas `konexio.fr` parce que ça tombe bien. Attribuer un site à une
entreprise sur une ressemblance, c'est exactement l'invention que le reste de la
chaîne existe pour empêcher — et c'est pire ici qu'ailleurs, parce qu'un site
attribué à tort entraîne derrière lui une catégorie, un score et une adresse.

`site_match` est à l'appartenance du site ce que `how` est à l'adresse et
`city_match` à la commune : un vocabulaire fermé qui dit **ce qui a été établi**,
accompagné de l'extrait qui l'établit.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable, Iterable

# --- Vocabulaire fermé de la preuve -----------------------------------------

SITE_MATCH_SIRET = 'siret affiché'
SITE_MATCH_SIREN = 'siren affiché'
SITE_MATCH_ADDRESS = 'adresse concordante'
SITE_MATCH_NAME = 'raison sociale'
SITE_MATCH_CONVERGENT = 'sources convergentes'
SITE_MATCH_NONE = 'aucun'

# Un SIRET vaut mieux qu'un SIREN, qui vaut mieux qu'une adresse, qui vaut mieux
# qu'un nom. La convergence de sources ferme la marche : elle dit seulement que
# plusieurs moteurs pointent le même domaine, ce qui est un indice d'usage, pas
# une déclaration de la structure.
SITE_MATCH_STRENGTH = {
    SITE_MATCH_NONE: 0,
    SITE_MATCH_CONVERGENT: 1,
    SITE_MATCH_NAME: 2,
    SITE_MATCH_ADDRESS: 3,
    SITE_MATCH_SIREN: 4,
    SITE_MATCH_SIRET: 5,
}

# --- Ce qui n'est jamais un site officiel ------------------------------------

# Annuaires d'entreprises et rediffuseurs de données légales. Ils citent le
# SIREN et l'adresse de leur fiche : ce sont donc les pages qui passeraient le
# mieux la vérification tout en n'appartenant jamais à la structure. Les exclure
# avant de vérifier, pas après.
DIRECTORY_HOSTS = {
    'societe.com', 'www.societe.com',
    'pappers.fr', 'www.pappers.fr', 'pappers.com',
    'manageo.fr', 'www.manageo.fr', 'manageo.com',
    'verif.com', 'www.verif.com',
    'infogreffe.fr', 'www.infogreffe.fr',
    'annuaire-entreprises.data.gouv.fr',
    'bodacc.fr', 'www.bodacc.fr',
    'kompass.com', 'fr.kompass.com',
    'pagesjaunes.fr', 'www.pagesjaunes.fr',
    'corporama.com', 'dirigeant.societe.com', 'bilansgratuits.fr',
    'entreprises.lefigaro.fr', 'sirene.fr', 'score3.fr', 'b-reputation.com',
}

# Plateformes, réseaux et places de marché : une page profil n'est pas un site.
PROFILE_HOST_PARTS = (
    'linkedin.', 'facebook.', 'instagram.', 'twitter.', 'x.com', 'youtube.',
    'tiktok.', 'pinterest.', 'malt.fr', 'codeur.com', 'fiverr.com', 'upwork.com',
    'indeed.', 'hellowork.', 'welcometothejungle.', 'glassdoor.',
    'google.', 'bing.', 'duckduckgo.', 'wikipedia.', 'crunchbase.',
)

# Infrastructure : CDN, polices, assets. Ces domaines entrent dans la liste des
# graines parce qu'ils sont liés depuis les pages crawlées, et ressortent en
# « page d'accueil illisible ». Ce ne sont pas des candidats, ce sont des
# dépendances techniques.
INFRA_HOST_PARTS = (
    'gstatic.com', 'googleapis.com', 'cloudfront.net', 'akamai', 'fastly.net',
    'jsdelivr.net', 'unpkg.com', 'cdnjs.', 'fbcdn.net', 'gravatar.com',
    'w.org', 'cloudflare.com', 'cloudflareinsights.com', 'amazonaws.com',
    'bootstrapcdn.com', 'typekit.net', 'fontawesome.com', 'hotjar.com',
    'googletagmanager.com', 'google-analytics.com', 'doubleclick.net',
)
INFRA_HOST_PREFIXES = ('cdn.', 'static.', 'assets.', 'img.', 'images.', 'media.')

EXCLUSION_DIRECTORY = 'annuaire ou rediffuseur de données légales'
EXCLUSION_PROFILE = 'profil de plateforme, pas un site propre'
EXCLUSION_INFRA = 'domaine d’infrastructure (CDN, polices, assets)'

# Formes juridiques : « KONEXIO SAS » et « Konexio » sont la même structure, et
# « SAS » tout seul ne rapproche rien.
LEGAL_FORMS = {
    'sas', 'sasu', 'sarl', 'eurl', 'sa', 'sci', 'snc', 'scop', 'scic', 'sca',
    'selarl', 'eirl', 'gie', 'association', 'asso', 'fondation', 'societe',
    'société', 'entreprise', 'groupe', 'holding', 'cie', 'compagnie',
}

_WORD_RE = re.compile(r'[a-z0-9]+')
# Un séparateur entre deux chiffres est décoratif : « 123 456 789 » et
# « 123.456.789 » sont le même SIREN.
_DIGIT_SEPARATOR_RE = re.compile(r'(?<=\d)[\s.\u00a0\-]+(?=\d)')


def _strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize('NFD', value)
    return ''.join(c for c in decomposed if unicodedata.category(c) != 'Mn')


def normalize_label(value: str | None) -> str:
    """Minuscules, sans accents, sans forme juridique, mots séparés par un espace."""
    words = _WORD_RE.findall(_strip_accents(str(value or '')).lower())
    kept = [w for w in words if w not in LEGAL_FORMS and len(w) > 1]
    return ' '.join(kept or words)


def host_of(url: str) -> str:
    match = re.match(r'^[a-z]+://([^/]+)', str(url or '').strip(), re.I)
    return (match.group(1) if match else '').lower()


def _domain_label(host: str) -> str:
    """Le nom enregistré du domaine, sans `www`, sans extension, sans séparateur.

    `www.konexio-formation.fr` → `konexioformation`. C'est cette forme-là qu'on
    compare à la raison sociale, et on la compare par **égalité** : voir
    `verify_site`.
    """
    bare = (host or '').lower()
    bare = bare[4:] if bare.startswith('www.') else bare
    label = bare.split('.')[0] if bare else ''
    return normalize_label(label.replace('-', ' ')).replace(' ', '')


def exclusion_reason(url: str) -> str | None:
    """Dit pourquoi cette URL ne peut pas être un site officiel, ou `None`."""
    host = host_of(url)
    if not host:
        return 'URL sans domaine lisible'
    bare = host[4:] if host.startswith('www.') else host
    if host in DIRECTORY_HOSTS or bare in DIRECTORY_HOSTS:
        return EXCLUSION_DIRECTORY
    if any(part in host for part in PROFILE_HOST_PARTS):
        return EXCLUSION_PROFILE
    if any(part in host for part in INFRA_HOST_PARTS):
        return EXCLUSION_INFRA
    if any(host.startswith(prefix) for prefix in INFRA_HOST_PREFIXES):
        return EXCLUSION_INFRA
    return None


def _joined_digits(text: str) -> str:
    return _DIGIT_SEPARATOR_RE.sub('', str(text or ''))


def _contains_identifier(text: str, identifier: str | None) -> bool:
    """Cherche un SIREN/SIRET dans un texte, séparateurs décoratifs recollés."""
    digits = re.sub(r'\D', '', str(identifier or ''))
    if len(digits) not in (9, 14):
        return False
    # Bornes non chiffrées : un SIREN de 9 chiffres ne doit pas être « trouvé »
    # au milieu d'un numéro de téléphone ou d'un identifiant plus long.
    return re.search(rf'(?<!\d){re.escape(digits)}(?!\d)', _joined_digits(text)) is not None


def _address_evidence(text: str, legal_address: str | None) -> str | None:
    """Concordance d'adresse : code postal **et** nom de voie, jamais l'un seul.

    Un code postal isolé ne désigne qu'un quartier ; un nom de rue isolé se
    répète dans toute la France. Les deux ensemble, dans la même page, valent
    rapprochement — c'est le même seuil que `city_match` applique à la commune.
    """
    address = str(legal_address or '')
    postal = re.search(r'(?<!\d)((?:0[1-9]|[1-8]\d|9[0-8])\d{3})(?!\d)', address)
    if not postal:
        return None
    code = postal.group(1)
    haystack = f' {normalize_label(text)} '
    if code not in _joined_digits(text):
        return None
    # Seulement ce qui précède le code postal. Un siège s'écrit « 9 RUE X 75011
    # PARIS » : au-delà du code postal il n'y a que la commune, et la commune
    # n'est pas un nom de voie. Sans cette coupe, « nos bureaux sont à Paris
    # 75011 » concordait avec une adresse rue de la Pierre Levée — un faux
    # rapprochement qui aurait attribué un site à la mauvaise structure.
    street_part = address[:postal.start()]
    street_words = [
        w for w in normalize_label(street_part).split()
        if len(w) >= 4 and not w.isdigit()
        and w not in {'rue', 'avenue', 'boulevard', 'place', 'chemin', 'route',
                      'impasse', 'allee', 'quai', 'cours', 'passage', 'villa',
                      'square', 'cedex', 'bis', 'ter'}
    ]
    hit = next((w for w in street_words if f' {w} ' in haystack), None)
    if not hit:
        return None
    return f'code postal {code} et « {hit} » lus dans la page'


def verify_site(candidate: dict, pages: Iterable[tuple[str, str]],
                title: str = '', converging_sources: int = 0) -> tuple[str, str]:
    """Rend `(site_match, preuve)` pour un domaine face à un candidat du registre.

    `pages` est une suite de `(url, texte)` : accueil, mentions légales, contact.
    Les mentions légales sont l'endroit où une structure française écrit son
    SIREN — c'est la preuve la plus forte et la moins coûteuse à obtenir.
    """
    pages = list(pages)
    blob = ' '.join(text for _, text in pages)

    for url, text in pages:
        if _contains_identifier(text, candidate.get('siret')):
            return SITE_MATCH_SIRET, f'SIRET {candidate.get("siret")} affiché sur {url}'
    for url, text in pages:
        if _contains_identifier(text, candidate.get('siren')):
            return SITE_MATCH_SIREN, f'SIREN {candidate.get("siren")} affiché sur {url}'

    for url, text in pages:
        evidence = _address_evidence(text, candidate.get('legal_address'))
        if evidence:
            return SITE_MATCH_ADDRESS, f'{evidence} ({url})'

    # Le nom ne vaut que s'il **porte** la page : dans le domaine ou dans le
    # titre. Trouvé dans le corps du texte, il dit seulement que la page parle
    # de cette structure — un partenaire, un client, une actualité. C'est la
    # même distinction que `city_match` fait entre « adresse » et « mention ».
    name = normalize_label(candidate.get('name'))
    if name:
        compact = name.replace(' ', '')
        host = host_of(pages[0][0]) if pages else ''
        # Égalité, pas inclusion. `konexio` est contenu dans
        # `konexio-formation.fr`, qui est une **autre** structure : accepter
        # l'inclusion, c'est attribuer le site du premier homonyme venu — le
        # scénario précis que cette étape doit empêcher. Un domaine qui porte
        # des mots en plus est une autre marque tant que rien d'autre ne le
        # rattache.
        if compact and compact == _domain_label(host):
            return SITE_MATCH_NAME, f'raison sociale « {candidate.get("name")} » portée par le domaine {host}'
        if title and f' {name} ' in f' {normalize_label(title)} ':
            return SITE_MATCH_NAME, f'raison sociale « {candidate.get("name")} » dans le titre : « {title.strip()[:120]} »'

    if converging_sources >= 2:
        host = host_of(pages[0][0]) if pages else ''
        return SITE_MATCH_CONVERGENT, f'{converging_sources} sources indépendantes désignent {host}'

    if name and name in normalize_label(blob):
        # Explicitement **pas** une preuve : on le dit pour que le refus soit
        # relisible, au lieu de laisser croire qu'on n'a rien vu.
        return SITE_MATCH_NONE, f'nom cité dans la page, sans SIREN, adresse ni titre concordants'
    return SITE_MATCH_NONE, ''


def find_official_site(candidate: dict,
                       search: Callable[[str], list[str]],
                       crawl: Callable[[str], tuple[list[tuple[str, str]], str]],
                       max_candidates: int = 4) -> dict:
    """Cherche le site d'un candidat du registre et n'en retient un qu'avec preuve.

    `search(query) -> [url, …]`, `crawl(url) -> ([(url, texte), …], titre)` sont
    injectés : le module reste testable hors ligne, et la politique de requêtes
    appartient à l'appelant.

    Rend toujours les quatre clés, même bredouille : `website`, `site_match`,
    `site_match_evidence`, `site_candidates`. Un échec nommé vaut mieux qu'un
    champ absent, qui se relirait comme « pas cherché ».
    """
    name = str(candidate.get('name') or '').strip()
    outcome: dict[str, Any] = {
        'website': None,
        'site_match': SITE_MATCH_NONE,
        'site_match_evidence': '',
        'site_candidates': [],
    }
    if not name:
        outcome['site_candidates'].append(
            {'website': None, 'site_match': SITE_MATCH_NONE,
             'evidence': 'candidat sans raison sociale : rien à chercher'})
        return outcome

    commune = str(candidate.get('commune_label') or '').strip()
    queries = [f'{name} {commune}'.strip(), f'{name} site officiel'.strip()]
    if candidate.get('siren'):
        queries.insert(0, f'{name} {candidate["siren"]}')

    # Convergence = plusieurs **sources** indépendantes, pas plusieurs requêtes.
    # Trois requêtes qui contiennent toutes le nom et qu'on pose au même moteur
    # rendent évidemment le même domaine : c'est le même avis répété, pas une
    # confirmation. `search` peut donc rendre `url` ou `(url, source)` ; sans
    # source déclarée on compte une seule provenance, et la convergence ne
    # se déclenche jamais toute seule.
    sources_by_host: dict[str, set[str]] = {}
    order: list[str] = []
    seen_hosts: set[str] = set()
    for query in queries:
        try:
            hits = search(query) or []
        except Exception as exc:  # une panne de moteur n'invente pas de site
            outcome['site_candidates'].append(
                {'website': None, 'site_match': SITE_MATCH_NONE,
                 'evidence': f'recherche « {query} » indisponible ({exc})'})
            continue
        for hit in hits:
            url, source = (hit if isinstance(hit, (tuple, list)) else (hit, 'recherche'))
            reason = exclusion_reason(url)
            host = host_of(url)
            if reason:
                if host not in seen_hosts:
                    outcome['site_candidates'].append(
                        {'website': url, 'site_match': SITE_MATCH_NONE, 'evidence': reason})
                seen_hosts.add(host)
                continue
            if host not in seen_hosts:
                order.append(url)
            seen_hosts.add(host)
            sources_by_host.setdefault(host, set()).add(str(source))

    best: dict[str, Any] | None = None
    for url in order[:max_candidates]:
        try:
            pages, title = crawl(url)
        except Exception as exc:
            outcome['site_candidates'].append(
                {'website': url, 'site_match': SITE_MATCH_NONE,
                 'evidence': f'site injoignable ({exc})'})
            continue
        if not pages:
            outcome['site_candidates'].append(
                {'website': url, 'site_match': SITE_MATCH_NONE,
                 'evidence': 'aucune page lisible'})
            continue
        match, evidence = verify_site(
            candidate, pages, title=title,
            converging_sources=len(sources_by_host.get(host_of(url), ())))
        entry = {'website': url, 'site_match': match, 'evidence': evidence}
        outcome['site_candidates'].append(entry)
        if match != SITE_MATCH_NONE:
            if best is None or SITE_MATCH_STRENGTH[match] > SITE_MATCH_STRENGTH[best['site_match']]:
                best = entry
            if match == SITE_MATCH_SIRET:
                break  # rien ne bat un SIRET affiché : inutile de payer plus de pages

    if best:
        outcome.update({
            'website': best['website'],
            'site_match': best['site_match'],
            'site_match_evidence': best['evidence'],
        })
    return outcome
