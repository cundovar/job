#!/usr/bin/env python3
"""Prospection V2 agences/studios web IDF hors annonces.

Pipeline:
1) Collecte large: moteurs + pages annuaires connues utilisées comme sources de liens.
2) Candidats du registre public (Sirene/RNE) sur les codes postaux de la zone.
3) Extraction des domaines de vraies agences (les annuaires ne sont pas gardés comme résultats).
4) Crawl léger de plusieurs pages utiles par site.
5) Scoring plafonné par famille de signaux + zone géographique (--zone), puis
   verdict d'activité rendu par le Vérificateur sur l'auto-description du site.
6) Fusion registre / crawl / CSV par SIRET, SIREN, domaine puis nom.
7) Stockage page_texts (pour analyse agent) + sorties Markdown + JSON +
   front/public/data/agencies/latest.json.

Deux sources, deux rôles qui ne se confondent pas :

- le **web** dit ce qu'une structure fait, parce qu'elle l'écrit elle-même ;
- le **registre** dit qui est immatriculé et où est le siège, jamais l'activité.

Un code APE n'a donc jamais le droit de produire une catégorie, et un nom
proche d'un domaine n'a jamais le droit de produire une propriété de site.
"""
from __future__ import annotations

import html
import csv
import json
import math
import re
import ssl
import sys
import time
import urllib.parse
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, unquote, urljoin, urlparse
from urllib.request import Request, urlopen

# Racine déduite du fichier, jamais codée en dur : les chemins absolus précédents
# pointaient vers ~/apps/job-search-automation-package : c'est le clone du VPS, absent
# du poste de travail. Le script y tournait donc en écrivant dans le vide, et le cache
# du dépôt restait vide. Même convention que server/config.js (resolve(__dirname, '..')).
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / 'data'
FRONT_DIR = ROOT / 'front/public/data/agencies'
DEFAULT_OUT_DIR = ROOT / 'output' / 'agencies'
COMPANIES_CSV = ROOT / 'config' / 'companies.csv'
GEOCODE_CACHE = DATA_DIR / 'geocode_cache.json'

# `tools/` n'est pas un package et ce fichier est aussi chargé par `importlib`
# depuis les tests : le sys.path du processus appelant ne contient ni la racine
# ni `tools/`. On les ajoute explicitement plutôt que de dépendre du cwd.
for _import_root in (str(ROOT), str(ROOT / 'tools')):
    if _import_root not in sys.path:
        sys.path.insert(0, _import_root)

from agency_registry import (  # noqa: E402  (dépend du sys.path ci-dessus)
    NAF_AGENCE,
    NAF_FORMATION,
    RegistryClient,
    RegistryError,
    postal_codes_of,
    search_zone_candidates,
)
from company_analysis.duplicate import normalize_name  # noqa: E402
from company_analysis.verifier import classify_self_description  # noqa: E402

# Distance depuis l'adresse de référence de Cundo (point fixe, choisi par lui).
# Adresse relevée sur le site de chaque agence — jamais déduite, jamais devinée.
ORIGIN_ADDRESS = '21 Rue Monte-Cristo, 75020 Paris'
# Filets de sécurité si Nominatim échoue : BAN (autorité FR), puis point BAN enregistré.
# ⚠️ Nominatim exige « Rue Monte-Cristo » : « rue de la Monte-Cristo » renvoie 0 résultat.
ORIGIN_BAN_QUERY = '21 rue Monte Cristo, 75020 Paris'
ORIGIN_FALLBACK = (48.85536, 2.39845, 'Rue Monte Cristo 75020 Paris (point BAN enregistré)')
UA_NOMINATIM = {'User-Agent': 'prospection-agences-cundo/1.0 (recherche emploi)'}
CONTACT_PATHS_EXTRA = ['/contact', '/mentions-legales', '/agence', '/a-propos']
ADDR1 = re.compile(r'\d{1,4}(?:\s?(?:bis|ter))?\s*[, ]\s*(?:rue|avenue|av\.|bd|boulevard|place|villa|passage|impasse|cours)\s[^0-9\n]{3,70}?(75\d{3}|92\d{3}|93\d{3}|94\d{3})', re.I)
ADDR2 = re.compile(r'(?:rue|avenue|av\.|bd|boulevard|place|villa|passage|impasse)\s[^0-9\n]{3,60}?\b(\d{1,4}\w?)\s*,?\s*(750\d{2}|92\d{3}|93\d{3}|94\d{3})', re.I)
TOWNS = {  # centres approximatifs (distance flaggée ~approximative)
    'paris 20': (48.8640, 2.3995), '75020': (48.8640, 2.3995),
    'paris 19': (48.8819, 2.3866), '75019': (48.8819, 2.3866),
    'paris 11': (48.8594, 2.3765), '75011': (48.8594, 2.3765),
    'paris 12': (48.8403, 2.4468), '75012': (48.8403, 2.4468),
    'paris 10': (48.8748, 2.3600), '75010': (48.8748, 2.3600),
    'bagnolet': (48.8623, 2.4159), 'les lilas': (48.8762, 2.4229),
    'pré-saint-gervais': (48.8844, 2.4126), 'montreuil': (48.8639, 2.4442),
    'vincennes': (48.8438, 2.4399), 'saint-mandé': (48.8461, 2.4148),
    'charenton': (48.8228, 2.4159), 'fontenay-sous-bois': (48.8506, 2.4699),
}

SEARCH_QUERIES = [
    # Paris + stack cible
    'agence web WordPress React Paris',
    'agence WordPress headless Paris',
    'agence développement React WordPress Paris',
    'agence Next.js WordPress Paris',
    'studio digital WordPress React Paris',
    'studio développement web sur mesure Paris',
    'agence WooCommerce WordPress Paris',
    'agence PHP Symfony WordPress Paris',
    # Est IDF / villes utiles
    'agence web Montreuil WordPress',
    'agence digitale Montreuil développement web',
    'agence web Pantin WordPress',
    'studio web Bagnolet site internet',
    'agence web Vincennes WordPress',
    'agence web Saint-Denis développement web',
    'agence web Créteil WordPress',
    'agence digitale Val-de-Marne site internet',
    'agence web Seine-Saint-Denis WordPress',
    'studio digital Île-de-France WordPress React',
]

# Organismes / centres de formation au numérique — cible "formateur" de Cundo.
FORMATION_QUERIES = [
    'organisme de formation développeur web Paris',
    'centre de formation WordPress développement web Paris',
    'organisme de formation numérique Île-de-France',
    'école développement web Paris',
    'bootcamp développeur web Paris',
    'formation reconversion développeur web Île-de-France',
    'organisme formation accessibilité numérique RGAA',
    'centre formation webmaster WordPress',
    'organisme formation web développement Paris',
]

# Ces pages peuvent être des annuaires/comparateurs : on les utilise pour découvrir
# des liens sortants, mais on ne les garde jamais comme agence finale.
DIRECTORY_SEEDS = [
    'https://www.lafabriquedunet.fr/agences/pages/agences-wordpress-ile-de-france-paris',
    'https://www.impli.fr/agences/wordpress-paris',
    'https://www.sortlist.fr/wordpress/paris-idf-fr',
    'https://www.sortlist.fr/web/paris-idf-fr',
    'https://www.sortlist.fr/developpement-site-internet/paris-idf-fr',
]

# Organismes de formation connus (cible "formateur" de Cundo) — garantis même si
# les moteurs de recherche throttlent. Domaine vérifié avant ajout.
FORMATION_ROOTS = [
    ('https://www.lewagon.com/fr', 'Le Wagon — bootcamp développeur web'),
    ('https://www.oclock.io/', "O'clock — école développeur web"),
    ('https://3wa.fr/', '3W Academy — formation développeur web'),
    ('https://www.wf3.fr/', 'WebForce3 — formation développement web'),
    ('https://www.wildcodeschool.com/', 'Wild Code School — formation dev web'),
    ('https://simplon.co/', 'Simplon — formation numérique & insertion'),
    ('https://lacapsule.academy/', 'La Capsule — bootcamp dev web'),
    ('https://www.studi.com/', 'Studi — formation web & numérique'),
    ('https://access42.net/', 'Access42 — accessibilité numérique RGAA + formation'),
    ('https://atalan.fr/', 'Atalan — accessibilité numérique + formation'),
]

CITY_TERMS = [
    'paris', 'ile-de-france', 'île-de-france', 'idf', '75', '92', '93', '94', '77',
    'montreuil', 'pantin', 'bagnolet', 'vincennes', 'saint-denis', 'créteil', 'creteil',
    'champigny', 'ivry', 'noisy', 'fontenay', 'val-de-marne', 'seine-saint-denis',
]

ZONES = {
    'ile-de-france': {
        'label': 'Île-de-France',
        'tier1': CITY_TERMS,
        'tier2': [],
    },
    'paris-20': {
        'label': 'Paris 20e et est parisien',
        'tier1': [
            '75020', 'paris 20', '20ème', '20eme', '20e arr',
            'ménilmontant', 'menilmontant', 'belleville', 'gambetta',
            'père-lachaise', 'pere lachaise', 'charonne', 'bercy', 'picpus',
            'saint-fargeau', 'saint blaise', 'nation',
        ],
        'tier2': [
            'paris', '75010', '75011', '75012', '75019',
            '11ème', '12ème', '19ème', '10ème', '11e arr', '12e arr', '19e arr', '10e arr',
            'montreuil', 'bagnolet', 'vincennes', 'fontenay-sous-bois',
            'saint-mandé', 'saint-mande', 'les lilas', 'rosny-sous-bois',
            'pré-saint-gervais', 'pre-saint-gervais',
        ],
    },
    'paris-19': {
        'label': 'Paris 19e et nord-est parisien',
        'tier1': [
            '75019', 'paris 19', '19ème', '19eme', '19e arr',
            'buttes-chaumont', 'buttes chaumont', 'la villette', 'villette',
            'ourcq', 'bassin de la villette', 'place des fêtes', 'place des fetes',
            'stalingrad', 'jaurès', 'jaures', 'crimée', 'crimee',
            'butte bergeyre', 'danube', 'amérique', 'amerique', 'pont de flandre',
            'belleville',
        ],
        'tier2': [
            'paris', '75010', '75018', '75020',
            '10ème', '18ème', '20ème', '10e arr', '18e arr', '20e arr',
            'pantin', 'aubervilliers', 'la courneuve', 'la plaine saint-denis',
            'pré-saint-gervais', 'pre-saint-gervais', 'les lilas',
            'menilmontant', 'ménilmontant', 'bagnolet',
        ],
    },
    'ouest-paris': {
        'label': 'Ouest de Paris (75 ouest, 92, 78)',
        'tier1': [
            '75015', '75016', '75017', '15ème', '16ème', '17ème',
            '15e arr', '16e arr', '17e arr',
            'boulogne-billancourt', 'boulogne billancourt', 'boulogne',
            'neuilly-sur-seine', 'neuilly sur seine', 'neuilly',
            'levallois', 'issy-les-moulineaux', 'issy les moulineaux', 'issy',
            'puteaux', 'nanterre', 'courbevoie', 'rueil-malmaison',
            'rueil malmaison', 'rueil', 'suresnes', 'saint-cloud', 'saint cloud',
            'viroflay', 'versailles', 'le chesnay', 'chesnay', 'clamart',
            'meudon', 'montrouge', 'vanves', 'malakoff', 'sèvres', 'sevres',
            'houilles', 'sartrouville', 'maisons-laffitte', 'le pecq',
            'marly-le-roi', 'bougival', 'croissy', 'carrières-sur-seine',
            'carrieres-sur-seine', 'hauts-de-seine', 'yvelines',
        ],
        'tier2': ['paris', 'ile-de-france', 'île-de-france', 'idf'],
    },
}

ZONE_QUERIES = {
    'paris-20': [
        'agence web Paris 20 WordPress',
        'agence digitale Paris 20e site internet',
        'studio web Belleville Ménilmontant agence',
        'agence web Gambetta Charonne création site',
    ],
    'paris-19': [
        'agence web Paris 19 WordPress',
        'agence digitale Paris 19e création site internet',
        'studio web Buttes-Chaumont La Villette agence',
        'agence web Ourcq Belleville développement',
        'agence web Bassin de la Villette site sur mesure',
    ],
    'ouest-paris': [
        'agence web Boulogne-Billancourt WordPress',
        'agence digitale Levallois développement web',
        'agence web Neuilly WordPress React',
        'studio web Issy-les-Moulineaux site internet',
        'agence web Versailles WordPress',
    ],
    'ile-de-france': [],
}


_TERM_PATTERNS: dict[str, re.Pattern] = {}


def term_pattern(term: str) -> re.Pattern:
    """Motif borné pour un terme de barème ou de zone.

    La recherche en sous-chaîne rapprochait des choses sans rapport : « nation »
    se déclenchait sur « international », « api » sur « rapide », « 75020 » sur
    « 750201 ». Chaque faux positif ajoutait des points, et le score cessait de
    vouloir dire quelque chose.

    Les bornes ne sont pas `\\b` : un terme peut commencer ou finir par un
    caractère non-mot (« next.js », « av. », « sur-mesure »). On exige donc
    l'absence de caractère de mot juste avant et juste après.
    """
    pattern = _TERM_PATTERNS.get(term)
    if pattern is None:
        pattern = re.compile(rf'(?<!\w){re.escape(term)}(?!\w)', re.I)
        _TERM_PATTERNS[term] = pattern
    return pattern


def has_term(blob: str, term: str) -> bool:
    return term_pattern(term).search(blob) is not None


def zone_of(blob: str, zone_key: str) -> tuple[str, str]:
    """Renvoie (tier1|tier2|none, terme trouvé) pour le blob texte donné."""
    zone = ZONES.get(zone_key)
    if not zone:
        return 'none', ''
    for term in zone['tier1']:
        if has_term(blob, term):
            return 'tier1', term
    for term in zone['tier2']:
        if has_term(blob, term):
            return 'tier2', term
    return 'none', ''


GENERIC_LABELS = {'voir', 'accueil', 'home', 'menu', 'plus', 'ici', 'site',
                  'agence', 'contact', 'le site', 'notre agence', 'l agence'}


def clean_label(label: str, base: str) -> str:
    """Nom affichable : si le label scrapé est un texte de menu (« Voir »), retombe sur le domaine."""
    l = (label or '').strip()
    if l and len(l) >= 4 and l.lower() not in GENERIC_LABELS:
        return l
    host = host_of(base)
    if not host:
        return l or host
    b = host.split('.')[0]
    return (b[:1].upper() + b[1:]) if b else l


STACK_POINTS = {
    'wordpress': 25, 'woocommerce': 14, 'react': 20, 'next.js': 18, 'nextjs': 18,
    'headless': 16, 'jamstack': 12, 'strapi': 8, 'api': 8, 'php': 8, 'symfony': 10,
    'vue': 8, 'nuxt': 8, 'drupal': 5, 'shopify': 5, 'webflow': 3,
    'accessibilité': 6, 'accessibilite': 6, 'rgaa': 6, 'wcag': 5,
}
AGENCY_POINTS = {
    'agence web': 10, 'agence digitale': 8, 'studio digital': 8, 'studio web': 8,
    'création de site': 8, 'creation de site': 8, 'développement web': 8,
    'developpement web': 8, 'site sur mesure': 8, 'sites sur mesure': 8,
    'sur-mesure': 5, 'portfolio': 4, 'réalisations': 4, 'realisations': 4,
}
FORMATION_POINTS = {
    'organisme de formation': 25, 'centre de formation': 25, 'organisme formation': 25,
    'centre formation': 22, 'formation professionnelle': 20, 'formation certifiante': 20,
    'formation développeur': 22, 'formation developpeur': 22, 'formation wordpress': 22,
    'formation web': 18, 'formation numérique': 20, 'formation numerique': 20,
    'reconversion': 16, 'reconversion professionnelle': 18, 'qualiopi': 20,
    'rncp': 14, 'titre professionnel': 16, 'bootcamp': 15,
    'école de code': 18, 'ecole de code': 18, 'formateur': 12,
    'alternance': 8, 'apprentissage': 8, 'certification': 6,
}
NEGATIVE = {
    'esn': -12, 'ssii': -15, 'cybersécurité': -8, 'cybersecurite': -8,
    'comparateur': -20, 'annuaire': -25,
}

# Plafonds par famille. Sans eux, dix synonymes de « formation » sur une même
# page suffisaient à atteindre 100 : tout le haut du classement se valait, et le
# score ne présélectionnait plus rien. Un signal répété n'apporte pas dix fois
# la même information.
FAMILY_CAPS = {'stack': 35, 'agence': 25, 'formation': 25}
ZONE_CAP = 25
CONTACT_CAP = 15

# Produits en libre-service et places de marché. Ce ne sont pas des employeurs
# du type recherché : on y achète un abonnement, on n'y candidate pas.
PLATFORM_HOSTS = {
    'webflow.com', 'wix.com', 'squarespace.com', 'shopify.com', 'shopify.fr',
    'wordpress.com', 'jimdo.com', 'strikingly.com', 'framer.com', 'canva.com',
    'hubspot.com', 'hubspot.fr', 'mailchimp.com', 'salesforce.com',
    'udemy.com', 'coursera.org', 'openclassrooms.com', 'livementor.com',
    'malt.fr', 'codeur.com', 'fiverr.com', 'upwork.com', 'comeup.com',
}

# Il en faut **deux** pour écarter : une agence qui parle de la plateforme d'un
# client emploie légitimement ces mots. Un faux écart coûte plus cher qu'un
# `incertain`, puisqu'il retire silencieusement une cible du champ de vision.
PLATFORM_TEXT_PATTERNS = [
    'essai gratuit', 'commencez gratuitement', 'start for free', 'sans engagement',
    'sans coder', 'no-code', 'nocode', 'créez votre site en quelques minutes',
    'plans et tarifs', 'abonnement mensuel', 'par mois et par utilisateur',
    'plateforme saas', 'notre plateforme tout-en-un', 'inscrivez-vous gratuitement',
    'trouvez un prestataire', 'trouvez un freelance', 'mettons en relation',
]
MIN_PLATFORM_SIGNALS = 2
CONTACT_HINTS = ['contact', 'recrutement', 'jobs', 'carriere', 'carrière', 'nous-rejoindre', 'nous rejoindre']
CRAWL_PATHS = [
    '/', '/agence', '/a-propos', '/services', '/realisations', '/portfolio',
    '/contact', '/recrutement', '/nous-rejoindre',
]
BAD_HOST_PARTS = [
    'google.', 'bing.', 'duckduckgo.', 'facebook.', 'instagram.', 'linkedin.', 'youtube.',
    'pinterest.', 'twitter.', 'x.com', 'github.', 'npmjs.', 'wikipedia.', 'societe.com',
    'verif.com', 'pagesjaunes.fr', 'indeed.', 'hellowork.', 'welcometothejungle.',
]
DIRECTORY_HOSTS = {
    'sortlist.fr', 'sortlist.com', 'clutch.co', 'lafabriquedunet.fr', 'impli.fr',
    'designrush.com', 'goodfirms.co', 'techbehemoths.com', 'sortlist.be',
}
DIRECTORY_TEXT_PATTERNS = [
    'top 10', 'top 25', 'meilleures agences', 'comparatif', 'comparer les agences',
    'trouver une agence', 'agences référencées', 'agences referencees', 'avis vérifiés',
    'avis verifies', 'prestataires sélectionnés', 'prestataires selectionnes',
]

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            attrs = dict(attrs)
            self._href = attrs.get('href')
            self._text = []
    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)
    def handle_endtag(self, tag):
        if tag == 'a' and self._href is not None:
            txt = ' '.join(' '.join(self._text).split())
            self.links.append((self._href, txt))
            self._href = None
            self._text = []


def fetch(url: str, timeout=6, max_bytes=700_000) -> str:
    req = Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/121 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.7',
    })
    ctx = ssl.create_default_context()
    with urlopen(req, timeout=timeout, context=ctx) as r:
        raw = r.read(max_bytes)
        charset = r.headers.get_content_charset() or 'utf-8'
        return raw.decode(charset, errors='ignore')


def strip_text(s: str) -> str:
    s = re.sub(r'<script.*?</script>|<style.*?</style>|<noscript.*?</noscript>', ' ', s, flags=re.I|re.S)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = html.unescape(s)
    return re.sub(r'\s+', ' ', s).strip()


def geocode(q: str):
    """Géocode via Nominatim (OSM). ~1,1 s entre appels (rate limit), countrycodes=fr."""
    try:
        url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode(
            {'q': q, 'format': 'json', 'limit': 1, 'countrycodes': 'fr'})
        with urlopen(Request(url, headers=UA_NOMINATIM), timeout=12) as r:
            res = json.loads(r.read().decode('utf-8'))
        time.sleep(1.1)
        if res:
            return float(res[0]['lat']), float(res[0]['lon']), res[0].get('display_name', '')
    except Exception:
        time.sleep(1.1)
    return None, None, ''


def geocode_ban(q: str):
    """Géocode via la Base Adresse Nationale (autorité France), repli de Nominatim."""
    try:
        url = 'https://api-adresse.data.gouv.fr/search?' + urllib.parse.urlencode({'q': q, 'limit': 1})
        with urlopen(Request(url, headers=UA_NOMINATIM), timeout=12) as r:
            res = json.loads(r.read().decode('utf-8'))
        time.sleep(1.1)
        f = (res.get('features') or [None])[0]
        if f:
            c = f['geometry']['coordinates']
            return float(c[1]), float(c[0]), f['properties'].get('label', '')
    except Exception:
        time.sleep(1.1)
    return None, None, ''


def normalized_address(address: str) -> str:
    return re.sub(r'\s+', ' ', str(address or '')).strip().casefold()


def load_geocode_cache(path: Path = GEOCODE_CACHE) -> dict[str, dict]:
    """Coordonnées déjà résolues, indexées par adresse normalisée."""
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_geocode_cache(cache: dict, path: Path = GEOCODE_CACHE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8'
    )


def geocode_cached(address: str, cache: dict) -> tuple[float | None, float | None, str]:
    """Géocode une adresse une fois, ici et dans les runs suivants.

    Seuls les succès sont mémorisés. Mémoriser un échec économiserait un appel,
    mais une coupure réseau d'une minute figerait pour toujours des adresses
    parfaitement géocodables en « position inconnue ».
    """
    key = normalized_address(address)
    if not key:
        return None, None, ''
    hit = cache.get(key)
    if isinstance(hit, dict):
        return hit.get('lat'), hit.get('lon'), hit.get('label') or ''
    lat, lon, label = geocode(address)
    if lat is None:
        lat, lon, label = geocode_ban(address)
    if lat is not None:
        cache[key] = {'lat': lat, 'lon': lon, 'label': label}
    return lat, lon, label


def haversine(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(h))


def find_address(blob: str) -> str:
    m = ADDR1.search(blob) or ADDR2.search(blob)
    return re.sub(r'\s+', ' ', m.group(0).strip().rstrip(',;')) if m else ''


def postal_code_from_address(address: str | None) -> str | None:
    """Extrait un code postal uniquement d'une adresse effectivement relevée."""
    if not address:
        return None
    match = re.search(r'\b(75\d{3}|92\d{3}|93\d{3}|94\d{3})\b', address)
    return match.group(1) if match else None


ORIGIN_CSV = 'csv'
ORIGIN_REGISTRY = 'registre'
ORIGIN_WEB = 'web'

UNCERTAIN_IDENTITY = 'nom normalisé (incertain)'
CERTAIN_IDENTITY = ('siret', 'siren', 'domaine')
IDENTITY_STRENGTH = {'': 0, UNCERTAIN_IDENTITY: 1, 'domaine': 2, 'siren': 3, 'siret': 4}


def identity_keys(record: dict) -> list[tuple[str, str]]:
    """Clés d'identité d'une fiche, de la plus sûre à la moins sûre.

    Les trois premières sont des identifiants : un SIRET, un SIREN et un domaine
    désignent une structure et une seule. La quatrième est une ressemblance —
    deux « Studio Bleu » normalisés pareil peuvent être deux sociétés.
    """
    keys: list[tuple[str, str]] = []
    siret = str(record.get('siret') or '').strip()
    siren = str(record.get('siren') or '').strip()
    host = host_of(str(record.get('website') or ''))
    name = normalize_name(record.get('name') or '')
    if siret:
        keys.append(('siret', f'siret:{siret}'))
    if siren:
        keys.append(('siren', f'siren:{siren}'))
    if host:
        keys.append(('domaine', f'host:{host}'))
    if name:
        keys.append((UNCERTAIN_IDENTITY, f'name:{name}'))
    return keys


def _stronger(left: str, right: str) -> str:
    return left if IDENTITY_STRENGTH.get(left, 0) >= IDENTITY_STRENGTH.get(right, 0) else right


def merge_records(records: list[dict]) -> list[dict]:
    """Réunit les fiches qui désignent la même structure, sans rien attribuer d'office.

    Ordre de dédoublonnage : SIRET, SIREN, domaine, puis nom normalisé. Un
    rapprochement par nom seul produit bien **une seule fiche**, mais il est
    marqué `identity_match: 'nom normalisé (incertain)'`, et dans ce cas
    l'identité administrative du registre (SIREN, SIRET, siège) reste dans
    `identity_candidates` au lieu de monter dans la fiche : sans cela, un
    homonyme suffirait à publier le site d'une société sous le SIREN d'une
    autre, et l'adresse d'un siège deviendrait celle d'une agence.

    Quand deux clés d'une même fiche pointent vers deux groupes différents,
    c'est un conflit d'identité : on le nomme dans `identity_conflicts` au lieu
    de fusionner les deux groupes, parce que fusionner serait trancher.
    """
    index: dict[str, int] = {}
    groups: list[dict] = []

    for record in records:
        keys = identity_keys(record)
        hits: dict[int, str] = {}
        for kind, key in keys:
            slot = index.get(key)
            if slot is not None and slot not in hits:
                hits[slot] = kind

        if not hits:
            groups.append({'members': [record], 'match': '', 'conflicts': []})
            target = len(groups) - 1
        else:
            target = next(iter(hits))  # clés parcourues de la plus sûre à la moins sûre
            group = groups[target]
            group['members'].append(record)
            group['match'] = _stronger(group['match'], hits[target])
            for other in list(hits)[1:]:
                group['conflicts'].append({
                    'via': hits[other],
                    'autre': str(groups[other]['members'][0].get('name') or ''),
                })
        for _, key in keys:
            index.setdefault(key, target)

    return [compose_record(group) for group in groups]


def compose_record(group: dict) -> dict:
    """Assemble une fiche unique à partir de ses membres, source par source.

    Priorité : le CSV versionné d'abord (c'est la voie de correction humaine),
    le registre pour l'adresse légale, le site pour l'adresse publiée et tout
    ce qui vient du crawl.
    """
    members = group['members']
    match = group['match']
    by_origin = {origin: [m for m in members if m.get('origin') == origin]
                 for origin in (ORIGIN_CSV, ORIGIN_REGISTRY, ORIGIN_WEB)}
    csv_rec = next(iter(by_origin[ORIGIN_CSV]), None)
    web_rec = next(iter(by_origin[ORIGIN_WEB]), None)
    registry_recs = by_origin[ORIGIN_REGISTRY]
    registry_rec = next(iter(registry_recs), None)

    merged = dict(web_rec or csv_rec or registry_rec or {})
    if csv_rec:
        merged['name'] = csv_rec['name']
        if csv_rec.get('website'):
            merged['website'] = csv_rec['website']
        if csv_rec.get('address'):
            merged['address'] = csv_rec['address']
            merged['postal_code'] = csv_rec.get('postal_code')
            merged['address_source'] = csv_rec['address_source']

    sources = set()
    for member in members:
        sources.update(member.get('sources') or [])
    merged['sources'] = sorted(sources)
    merged['origins'] = sorted({str(m.get('origin') or ORIGIN_WEB) for m in members})
    merged['identity_match'] = match
    merged['identity_conflicts'] = group['conflicts']
    merged.setdefault('website', None)

    # Le registre ne monte dans la fiche que si le rapprochement est un
    # identifiant, ou s'il n'y a rien d'autre dans le groupe à qui l'attribuer.
    promote = registry_rec is not None and (match in CERTAIN_IDENTITY or len(members) == 1)
    merged['identity_candidates'] = []
    if registry_rec and not promote:
        merged['identity_candidates'] = [
            {
                'name': rec.get('name'),
                'siren': rec.get('siren'),
                'siret': rec.get('siret'),
                'legal_address': rec.get('legal_address'),
                'source': 'registre — rapprochement par nom, non confirmé',
            }
            for rec in registry_recs
        ]
    # Un SIREN saisi à la main dans le CSV est une affirmation humaine : il prime
    # sur le registre et survit à un rapprochement incertain.
    merged['siren'] = (csv_rec or {}).get('siren') or (registry_rec.get('siren') if promote else None)
    merged['siret'] = registry_rec.get('siret') if promote else None
    merged['legal_address'] = registry_rec.get('legal_address') if promote else None
    merged['legal_address_source'] = registry_rec.get('legal_address_source') if promote else None
    if promote and registry_rec.get('why_candidate'):
        merged['registry_note'] = registry_rec['why_candidate']
    return merged


def load_curated_agencies(zone_key: str, path: Path = COMPANIES_CSV) -> list[dict]:
    """Charge les cibles versionnées afin qu'elles survivent à chaque nouveau crawl."""
    if not path.exists():
        return []
    with path.open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))

    curated = []
    for row in rows:
        name = (row.get('nom') or '').strip()
        if not name or (row.get('statut') or '').strip() == 'ecartee':
            continue
        address = (row.get('adresse') or '').strip() or None
        postal_code = (row.get('code_postal') or '').strip() or None
        if not address:
            postal_code = None
        blob = ' '.join(str(row.get(key) or '') for key in ('ville', 'adresse', 'code_postal')).lower()
        zone_match, zone_term = zone_of(blob, zone_key)
        curated.append({
            'name': name,
            'website': (row.get('site') or '').strip() or None,
            # Rempli à la main quand quelqu'un a vérifié l'immatriculation : c'est
            # la seule façon d'affirmer qu'un site et un SIREN vont ensemble.
            'siren': (row.get('siren') or '').strip() or None,
            'origin': ORIGIN_CSV,
            'score': 0,
            'raw_score': 0,
            'stack': [],
            'emails': [],
            'contact_urls': [],
            'reasons': ['cible versionnée dans config/companies.csv'],
            'sources': ['config/companies.csv'],
            'fetched_pages': [],
            'snippet': '',
            'zone_match': zone_match,
            'zone_term': zone_term,
            'category': 'agence',
            'category_reason': 'retenue à la main dans config/companies.csv',
            'category_evidence': [],
            'page_texts': [],
            'address': address,
            'postal_code': postal_code,
            'address_source': 'relevé à la main (config/companies.csv)' if address else None,
            'distance_m': None,
        })
    return curated


def excluded_hosts_from_csv(path: Path = COMPANIES_CSV) -> dict[str, str]:
    """Hôtes qu'un humain a explicitement écartés dans le CSV versionné.

    Une exclusion décidée à la main ne doit pas être redécouverte à chaque run :
    sans cela, la même cible remonte, est réévaluée, et finit par repasser.
    """
    if not path.exists():
        return {}
    with path.open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    excluded = {}
    for row in rows:
        if (row.get('statut') or '').strip() != 'ecartee':
            continue
        host = host_of((row.get('site') or '').strip())
        if host:
            excluded[host] = (row.get('nom') or '').strip()
    return excluded


def merge_curated_agencies(results: list[dict], zone_key: str, path: Path = COMPANIES_CSV) -> list[dict]:
    """Fusionne le crawl avec le CSV, en donnant priorité aux relevés manuels."""
    crawled = [{**agency, 'origin': agency.get('origin', ORIGIN_WEB)} for agency in results]
    return merge_records(crawled + load_curated_agencies(zone_key, path))


def fmt_distance(m) -> str:
    if m is None:
        return 'inconnue'
    return f'{m} m' if m < 1000 else f'{m / 1000:.1f}'.replace('.', ',') + ' km'


LEGAL_ADDRESS_LABEL = 'siège déclaré au registre'


def _set_position(agency: dict, origin: tuple, address: str, source: str, cache: dict) -> bool:
    """Pose l'adresse et la distance si, et seulement si, le géocodage aboutit."""
    lat, lon, _ = geocode_cached(address + ', France', cache)
    if lat is None:
        return False
    agency['address'] = address
    agency['postal_code'] = postal_code_from_address(address)
    agency['address_source'] = source
    agency['distance_m'] = round(haversine(origin, (lat, lon)))
    return True


def enrich_with_distances(results: list[dict], cache: dict | None = None) -> str:
    """Ajoute address / address_source / distance_m à chaque agence.

    Cinq origines possibles, dans cet ordre de confiance : le relevé manuel du
    CSV, l'adresse publiée sur les pages crawlées, celle de /contact ou des
    mentions légales, le siège déclaré au registre, puis — en dernier recours et
    clairement marqué — le centre de la commune. Rien n'est jamais déduit d'un
    code postal seul. Sans aucune de ces cinq, `distance_m` reste `None`.

    Le géocodage passe par un cache disque : deux runs sur les mêmes adresses ne
    rappellent ni Nominatim ni la BAN. Renvoie les coords origine.
    """
    cache = load_geocode_cache() if cache is None else cache
    o_lat, o_lon, o_disp = geocode_cached(ORIGIN_ADDRESS, cache)
    if o_lat is None:
        o_lat, o_lon, o_disp = geocode_cached(ORIGIN_BAN_QUERY, cache)
    if o_lat is None:
        o_lat, o_lon, o_disp = ORIGIN_FALLBACK
        print(f"WARN: géocodage origine en échec — point BAN enregistré utilisé ({o_lat}, {o_lon})")
    origin = (o_lat, o_lon)
    print(f"DISTANCES depuis {ORIGIN_ADDRESS} → {o_lat:.5f},{o_lon:.5f}")
    for a in results:
        a.setdefault('address', None)
        a.setdefault('postal_code', None)
        a.setdefault('address_source', None)
        a['distance_m'] = None

        if a['address']:
            lat, lon, _ = geocode_cached(a['address'] + ', France', cache)
            if lat is not None:
                a['postal_code'] = a.get('postal_code') or postal_code_from_address(a['address'])
                a['distance_m'] = round(haversine(origin, (lat, lon)))
            # Un relevé manuel reste prioritaire même si son géocodage échoue :
            # le crawl ne doit pas remplacer une donnée versionnée par une
            # extraction automatique moins fiable.
            continue

        blob = (a.get('snippet') or '') + ' ' + ' '.join(p.get('text', '') for p in (a.get('page_texts') or []))
        found = find_address(blob)
        if found and _set_position(a, origin, found, 'site (pages crawlées)', cache):
            continue

        host = host_of(a.get('website') or '')  # passe 2 : /contact souvent hors crawl
        for path in CONTACT_PATHS_EXTRA:
            if not host:
                break
            try:
                txt = strip_text(fetch(f'https://{host}{path}', timeout=8, max_bytes=400_000))
            except Exception:
                continue
            found = find_address(txt)
            if found and _set_position(a, origin, found, f'site ({path})', cache):
                break
            time.sleep(0.2)
        if a['distance_m'] is not None:
            continue

        legal = a.get('legal_address')
        if legal and _set_position(a, origin, legal, f'{LEGAL_ADDRESS_LABEL} (Sirene/RNE)', cache):
            continue

        approx = next((k for k in TOWNS if k in blob.lower()), None)
        if approx:
            a['address_source'] = f'~centre {approx} (approximatif)'
            a['distance_m'] = round(haversine(origin, TOWNS[approx]))
    return f'{o_lat:.5f},{o_lon:.5f}'


def address_how(agency: dict) -> str:
    """Vocabulaire du contrat de sortie : *comment* la position a été obtenue.

    C'est la garantie anti-invention. « adresse » et « contact/legales » viennent
    d'une adresse lue sur le site ; « ville/arr (~centre) » n'est qu'un centre
    d'arrondissement, et ne vaut pas adresse. Sans position : chaîne vide.
    """
    source = agency.get('address_source') or ''
    if not source:
        return ''
    if source.startswith('~centre'):
        return 'ville/arr (~centre)'
    if source.startswith(LEGAL_ADDRESS_LABEL):
        return 'siège (registre)'
    if source.startswith('site (') and source != 'site (pages crawlées)':
        return 'contact/legales'
    return 'adresse'


def partition_by_radius(results: list[dict], radius_m: int) -> dict:
    """Range chaque agence selon sa distance à l'origine, et selon ce qu'on en sait.

    Quatre cas, pas trois : une position déduite du centre d'un arrondissement
    peut tomber sous le rayon sans qu'aucune adresse n'ait jamais été lue. La
    compter comme « dans le rayon » ferait passer une approximation pour un fait,
    ce qui est exactement la confusion à l'origine des agences inventées.
    """
    inside: list[dict] = []
    approximate: list[dict] = []
    outside: list[dict] = []
    unknown: list[dict] = []
    for agency in results:
        agency['how'] = address_how(agency)
        distance = agency.get('distance_m')
        if distance is None:
            unknown.append(agency)
        elif distance > radius_m:
            outside.append(agency)
        elif agency.get('address'):
            inside.append(agency)
        else:
            approximate.append(agency)
    return {
        'inside': inside,
        'approximate': approximate,
        'outside': outside,
        'unknown': unknown,
    }


def registry_record(candidate: dict, zone_key: str) -> dict:
    """Met un candidat du registre dans le format du pipeline, sans lui donner de verdict.

    `category` vaut `incertain` et pas autre chose : le registre n'a pas dit ce
    que fait cette structure, et un 62.01Z traduit en « agence » serait
    exactement l'invention que la chaîne existe pour empêcher. Le site reste
    `None` : le registre n'en publie aucun, et en deviner un à partir du nom
    reviendrait à attribuer un domaine.
    """
    blob = ' '.join(
        str(candidate.get(key) or '') for key in ('legal_address', 'commune_label', 'postal_code')
    ).lower()
    zone_match, zone_term = zone_of(blob, zone_key)
    return {
        'name': str(candidate.get('name') or '')[:160],
        'website': None,
        'siren': candidate.get('siren'),
        'siret': candidate.get('siret'),
        'origin': ORIGIN_REGISTRY,
        'score': 0,
        'raw_score': 0,
        'stack': [],
        'emails': [],
        'contact_urls': [],
        'reasons': [candidate.get('why_candidate', '')],
        'signals': {'positive': [], 'negative': [], 'exclusion': []},
        'family_scores': {'stack': 0, 'agence': 0, 'formation': 0},
        'sources': list(candidate.get('sources') or []),
        'fetched_pages': [],
        'snippet': '',
        'page_texts': [],
        'zone_match': zone_match,
        'zone_term': zone_term,
        'category': 'incertain',
        'category_reason': candidate.get('why_candidate', ''),
        'category_evidence': [],
        'activity_code': candidate.get('activity_code'),
        'address': None,
        'postal_code': None,
        'address_source': None,
        'distance_m': None,
        'legal_address': candidate.get('legal_address'),
        'legal_address_source': candidate.get('legal_address_source'),
    }


def registry_candidates(zone_key: str, client: RegistryClient | None = None) -> tuple[list[dict], list[str]]:
    """Candidats du registre sur les codes postaux de la zone, plus les avertissements.

    Deux silences volontaires, tous deux expliqués au lieu d'être subis :

    - une zone dont les termes ne contiennent aucun code postal explicite
      (« ile-de-france ») n'est pas interrogée : deviner ses communes
      reviendrait à choisir le périmètre de la recherche à la place de
      l'utilisateur ;
    - une panne du registre ne vide pas le résultat. Le crawl web continue seul
      et l'avertissement remonte jusqu'au payload, parce qu'une liste courte
      sans explication se relit comme « il n'y a rien ici ».
    """
    zone = ZONES.get(zone_key) or {}
    codes = postal_codes_of(list(zone.get('tier1', [])))
    if not codes:
        return [], [
            f"registre non interrogé : la zone « {zone_key} » ne porte aucun code postal explicite"
        ]
    try:
        raw = search_zone_candidates(
            postal_codes=codes,
            naf_codes=NAF_AGENCE + NAF_FORMATION,
            client=client or RegistryClient(),
        )
    except RegistryError as exc:
        return [], [f"registre indisponible ({exc}) — le crawl web continue seul"]
    return [registry_record(candidate, zone_key) for candidate in raw], []


def parse_links(page: str, base: str) -> list[tuple[str, str]]:
    lp = LinkParser(); lp.feed(page)
    out=[]
    for href, label in lp.links:
        if not href: continue
        if href.startswith('mailto:'):
            out.append((href, label)); continue
        if href.startswith('//'): href = 'https:' + href
        href = urljoin(base, href)
        if href.startswith('http'):
            out.append((href.split('#')[0], label))
    return out


def host_of(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix('www.')


def root_url(url: str) -> str:
    p = urlparse(url)
    if not p.scheme or not p.netloc: return ''
    return f'{p.scheme}://{p.netloc}/'


def is_bad_host(host: str) -> bool:
    return not host or any(b in host for b in BAD_HOST_PARTS)


def is_directory(host: str, title='', text='') -> bool:
    blob = f'{host} {title} {text[:10000]}'.lower()
    return host in DIRECTORY_HOSTS or any(p in blob for p in DIRECTORY_TEXT_PATTERNS)


def search_ddg(query: str, max_results=12) -> list[tuple[str, str, str]]:
    # DuckDuckGo HTML is unstable but useful when it responds.
    urls=[]
    for endpoint in ['https://duckduckgo.com/html/?q=', 'https://html.duckduckgo.com/html/?q=']:
        try:
            page = fetch(endpoint + quote_plus(query), timeout=10)
        except Exception:
            continue
        for href, label in parse_links(page, endpoint):
            if 'uddg=' in href:
                m = re.search(r'uddg=([^&]+)', href)
                if m: href = unquote(m.group(1))
            h=host_of(href)
            if href.startswith('http') and not is_bad_host(h) and not is_directory(h, label):
                urls.append((href, label, 'ddg:'+query))
            if len(urls) >= max_results: break
        if urls: break
    return urls


def search_bing(query: str, max_results=12) -> list[tuple[str, str, str]]:
    try:
        page = fetch('https://www.bing.com/search?q=' + quote_plus(query), timeout=10)
    except Exception:
        return []
    links=parse_links(page, 'https://www.bing.com/')
    out=[]
    for href,label in links:
        h=host_of(href)
        if not href.startswith('http') or is_bad_host(h) or is_directory(h, label):
            continue
        # Bing internal redirects/noise
        if 'bing.com' in h or '/ck/a' in href:
            continue
        out.append((href,label,'bing:'+query))
        if len(out)>=max_results: break
    return out


def clean_candidate_url(raw: str) -> str:
    raw = html.unescape(raw).strip().strip('"\'<> ,;')
    raw = raw.replace('\\/', '/')
    # Couper les artefacts JSON/HTML après les paramètres tracking.
    raw = re.split(r'(&quot;|"|<|>|\\n|\\r)', raw)[0]
    raw = raw.replace('&amp;', '&')
    # Retirer les paramètres annuaire/tracking pour revenir au domaine agence.
    if 'utm_source=' in raw:
        raw = raw.split('?utm_source=')[0].split('&utm_source=')[0]
    if raw.startswith('http://') or raw.startswith('https://'):
        return raw.split('#')[0]
    return ''


def extract_agency_links_from_directory(url: str) -> list[tuple[str,str,str]]:
    try:
        page=fetch(url, timeout=15, max_bytes=1_500_000)
    except Exception:
        return []
    links=parse_links(page,url)
    out=[]
    seed_host=host_of(url)

    def maybe_add(href: str, label: str):
        href = clean_candidate_url(href)
        h=host_of(href)
        if not href.startswith('http') or not h or h == seed_host or is_bad_host(h):
            return
        if h in DIRECTORY_HOSTS or h.endswith('lafabriquedunet.fr'):
            return
        if h.startswith('cdn.') or h.startswith('static.') or any(x in h for x in ['cloudflare', 'googleapis', 'schema.org']):
            return
        blob=(label+' '+href).lower()
        # Depuis les annuaires, les URLs tracking sont déjà des agences; garder plus large,
        # puis le crawl/scoring filtrera les faux positifs.
        if any(x in blob for x in ['agence','studio','web','wordpress','digital','site','développement','developpement']) or re.search(r'\.(fr|com|paris|agency)/?$', href):
            out.append((href,label or h,'directory:'+url))

    for href,label in links:
        maybe_add(href,label)

    # Les annuaires modernes stockent souvent les sites agences dans du JSON échappé.
    # Exemple: https://agence.fr/?utm_source=www.lafabriquedunet.fr&amp;utm_medium=agency...
    for m in re.finditer(r'https?://[^\s"\'<>]+', page):
        href = clean_candidate_url(m.group(0))
        maybe_add(href, host_of(href))

    # Dédupe par host en gardant le premier label/source.
    dedup={}
    for href,label,src in out:
        h=host_of(href)
        dedup.setdefault(h,(href,label,src))
    return list(dedup.values())


TITLE_RE = re.compile(r'<title[^>]*>(.*?)</title>', re.I | re.S)
META_DESCRIPTION_RE = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', re.I | re.S
)
HEADING_RE = re.compile(r'<h[12][^>]*>(.*?)</h[12]>', re.I | re.S)


def self_description_of(page: str) -> list[str]:
    """Ce que la page dit d'elle-même : title, meta description, h1/h2.

    C'est la seule matière que le Vérificateur a le droit d'utiliser pour
    trancher l'activité. Contrairement au texte intégral, elle ne contient pas
    les mots des clients, des études de cas ou du pied de page — là où « agence
    web » apparaît sur des sites qui n'en sont pas une.
    """
    parts: list[str] = []
    for pattern in (TITLE_RE, META_DESCRIPTION_RE):
        match = pattern.search(page)
        if match:
            parts.append(strip_text(match.group(1)))
    parts += [strip_text(m.group(1)) for m in list(HEADING_RE.finditer(page))[:6]]
    return [part for part in parts if part]


def crawl_site(base: str) -> tuple[str, list[tuple[str,str]], list[str], list[dict], list[str]]:
    texts=[]; all_links=[]; fetched=[]; pages=[]; description: list[str] = []
    for path in CRAWL_PATHS:
        url = urljoin(base, path.lstrip('/')) if path != '/' else base
        try:
            page=fetch(url, timeout=8, max_bytes=500_000)
        except Exception:
            continue
        if not description:
            description = self_description_of(page)
        text=strip_text(page)
        if text:
            texts.append(text[:25000]); fetched.append(url)
            pages.append({'url': url, 'text': text[:2500]})
        all_links.extend(parse_links(page,url))
        if len(fetched) >= 4:
            break
        time.sleep(0.15)
    return ' '.join(texts), all_links, fetched, pages, description


def _family_score(blob: str, points: dict[str, int], cap: int, label: str) -> tuple[int, list[str]]:
    """Somme plafonnée d'une famille de signaux, avec le détail de ce qui a compté."""
    matched = [(term, pts) for term, pts in points.items() if has_term(blob, term)]
    total = sum(pts for _, pts in matched)
    capped = min(total, cap)
    signals = [f'+{pts} {label}:{term}' for term, pts in matched]
    if total > capped:
        signals.append(f'plafond {label} : {total} ramené à {capped}')
    return capped, signals


def exclusion_reasons(host: str, name: str, text: str, excluded_hosts: dict[str, str] | None = None) -> list[str]:
    """Motifs d'écartement d'une cible, chacun nommé.

    Trois familles, et seulement trois : un annuaire, un produit en libre-service
    ou une exclusion décidée à la main dans le CSV versionné. Ne pas être une
    agence n'en fait pas partie : un organisme de formation vérifié reste une
    cible, et l'écarter au motif qu'il ne se décrit pas comme une agence ferait
    disparaître Access42 ou Simplon du champ.
    """
    blob = f'{host} {name} {text[:20000]}'.lower()
    reasons: list[str] = []
    if host in PLATFORM_HOSTS:
        reasons.append(f'produit en libre-service / place de marché connue ({host})')
    manual = (excluded_hosts or {}).get(host)
    if manual:
        reasons.append(f'écartée à la main dans config/companies.csv ({manual})')
    if is_directory(host, name, text):
        reasons.append('annuaire ou comparateur')
    platform_hits = [pattern for pattern in PLATFORM_TEXT_PATTERNS if pattern in blob]
    if len(platform_hits) >= MIN_PLATFORM_SIGNALS:
        reasons.append('libre-service : ' + ', '.join(platform_hits[:4]))
    return reasons


def score_candidate(
    name: str,
    base: str,
    text: str,
    links: list[tuple[str, str]],
    zone_key: str = '',
    self_description: list[str] | None = None,
    excluded_hosts: dict[str, str] | None = None,
) -> dict:
    """Présélection déterministe, puis verdict d'activité rendu par le Vérificateur.

    Le score n'est pas un jugement : c'est un tri. Le verdict, lui, vient de
    `classify_self_description`, c'est-à-dire des mots que la structure emploie
    pour se décrire — jamais d'un code APE, jamais d'un score élevé.
    """
    blob = (name + ' ' + base + ' ' + text).lower()
    positive: list[str] = []
    stack_score, stack_signals = _family_score(blob, STACK_POINTS, FAMILY_CAPS['stack'], 'stack')
    agency_score, agency_signals = _family_score(blob, AGENCY_POINTS, FAMILY_CAPS['agence'], 'agence')
    formation_score, formation_signals = _family_score(blob, FORMATION_POINTS, FAMILY_CAPS['formation'], 'formation')
    positive += stack_signals + agency_signals + formation_signals
    score = stack_score + agency_score + formation_score

    zone_match, zone_term = 'none', ''
    if zone_key:
        zone_match, zone_term = zone_of(blob, zone_key)
        if zone_match == 'tier1':
            score += ZONE_CAP
            positive.append(f'+{ZONE_CAP} zone:{zone_term}')
        elif zone_match == 'tier2':
            score += ZONE_CAP // 2
            positive.append(f'+{ZONE_CAP // 2} zone-large:{zone_term}')

    negative = []
    for term, pts in NEGATIVE.items():
        if has_term(blob, term):
            score += pts
            negative.append(f'{pts} {term}')

    emails = sorted(set(re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', text)))[:5]
    contact_urls = []
    for href, label in links:
        low = (href + ' ' + label).lower()
        if href.startswith('mailto:') or any(hint in low for hint in CONTACT_HINTS):
            contact_urls.append(href)
    seen = set()
    contact_urls = [x for x in contact_urls if not (x in seen or seen.add(x))][:6]
    contact_score = min(CONTACT_CAP, (8 if emails else 0) + (10 if contact_urls else 0))
    if contact_score:
        score += contact_score
        positive.append(f'+{contact_score} contact joignable (plafonné à {CONTACT_CAP})')

    stack = [
        term
        for term in ['WordPress', 'WooCommerce', 'React', 'Next.js', 'Headless', 'Jamstack',
                     'PHP', 'Symfony', 'Vue', 'Nuxt', 'Drupal', 'Shopify', 'Webflow', 'RGAA', 'WCAG']
        if has_term(blob, term.lower())
    ]

    exclusions = exclusion_reasons(host_of(base), name, text, excluded_hosts)
    # Le Vérificateur ne lit que l'auto-description ; à défaut, le texte crawlé,
    # qui reste ce que la structure a écrit sur elle-même.
    verdict = classify_self_description(list(self_description or []) or [name, text[:4000]])
    if exclusions:
        category, category_reason = 'ecarte', ' ; '.join(exclusions)
        category_evidence: list[str] = []
    else:
        category = verdict['category']
        category_reason = verdict['reason']
        category_evidence = verdict['evidence']

    return {
        'score': max(0, min(100, score)),
        'raw_score': score,
        'reasons': (positive + negative)[:16],
        'signals': {'positive': positive, 'negative': negative, 'exclusion': exclusions},
        'family_scores': {'stack': stack_score, 'agence': agency_score, 'formation': formation_score},
        'emails': emails,
        'contact_urls': contact_urls,
        'stack': stack,
        'agency_signal': category == 'agence',
        'formation_org': category == 'formation',
        'category': category,
        'category_reason': category_reason,
        'category_evidence': category_evidence,
        'directory_signal': bool(exclusions),
        'zone_match': zone_match,
        'zone_term': zone_term,
    }


# Une piste qui ne tranche pas doit mériter sa place ; une piste qui a tranché
# l'a déjà méritée.
UNCERTAIN_KEEP_SCORE = 50


def keeps_candidate(scored: dict) -> bool:
    """Le verdict décide de garder, le score ne décide que du rang.

    Un organisme de formation emploie peu du vocabulaire sur lequel le barème
    est calibré. Lui appliquer le même seuil qu'à une piste non qualifiée
    reviendrait à écarter un formateur *parce qu'il n'est pas une agence* —
    exactement ce que la cible « formateur » interdit.
    """
    if scored['category'] == 'ecarte':
        return False
    if scored['category'] == 'incertain':
        return scored['score'] >= UNCERTAIN_KEEP_SCORE
    return True


def run():
    # Zone géographique : --zone ile-de-france (défaut) | paris-20 | paris-19 | ouest-paris
    args = sys.argv[1:]
    out_dir = Path(args[args.index('--out') + 1]).expanduser().resolve() if '--out' in args else DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True); DATA_DIR.mkdir(parents=True, exist_ok=True); FRONT_DIR.mkdir(parents=True, exist_ok=True)
    zone_key = args[args.index('--zone') + 1] if '--zone' in args else 'ile-de-france'
    if zone_key not in ZONES:
        # Pas de repli silencieux : chercher une autre zone que celle demandée
        # sans le dire ferait croire à une passe ciblée qui n'a pas eu lieu.
        known = ', '.join(sorted(ZONES))
        print(f"Zone inconnue : « {zone_key} ». Zones disponibles : {known}.", file=sys.stderr)
        raise SystemExit(2)
    radius_m = None
    if '--radius' in args:
        raw = args[args.index('--radius') + 1]
        if not raw.isdigit() or int(raw) <= 0:
            print(f"Rayon invalide : « {raw} ». Attendu un nombre de mètres, ex. 2000.", file=sys.stderr)
            raise SystemExit(2)
        radius_m = int(raw)
        if '--no-distance' in args:
            # Un rayon sans mesure de distance ne filtrerait rien tout en
            # annonçant un périmètre : contradiction, pas une valeur par défaut.
            print("--radius exige les distances : retire --no-distance.", file=sys.stderr)
            raise SystemExit(2)
    zone = ZONES[zone_key]
    queries = SEARCH_QUERIES + FORMATION_QUERIES + ZONE_QUERIES.get(zone_key, [])
    seeds: list[tuple[str,str,str]]=[]
    # 1 search engines
    for q in queries:
        seeds.extend(search_ddg(q, max_results=8))
        seeds.extend(search_bing(q, max_results=8))
        time.sleep(0.5)
    # 2 directories as link sources
    for url in DIRECTORY_SEEDS:
        seeds.extend(extract_agency_links_from_directory(url))
        time.sleep(0.7)
    # 3 add known previous good roots to avoid regressions
    for url,label in [
        ('https://opus.paris/', 'Opus agence WordPress'),
        ('https://reactive-tech-solutions.com/', 'Reactive Tech Solutions'),
        ('https://www.wordpress-paris.com/', 'WordPress Paris'),
    ]:
        seeds.append((url,label,'known'))
    # 3b organismes de formation connus (cible formateur) — toujours crawlés
    for url,label in FORMATION_ROOTS:
        seeds.append((url,label,'known-formation'))

    # Dedupe by host
    by_host={}
    for href,label,source in seeds:
        base=root_url(href)
        h=host_of(base)
        if not base or is_bad_host(h) or h in DIRECTORY_HOSTS:
            continue
        if h not in by_host:
            by_host[h]={'base':base,'name':clean_label(label, base),'sources':set()}
        by_host[h]['sources'].add(source)

    excluded_hosts = excluded_hosts_from_csv()
    results=[]; scanned=0; ecartes=[]
    for h,c in list(by_host.items())[:75]:
        scanned += 1
        text,links,fetched,pages,description=crawl_site(c['base'])
        if not text:
            # still keep known if it has name signal? no, avoid empty except previous wordpress-paris 403
            if c['base'] != 'https://www.wordpress-paris.com/':
                continue
        scored=score_candidate(c['name'], c['base'], text, links, zone_key, description, excluded_hosts)
        if scored['category'] == 'ecarte':
            # Un écarté reste nommé avec son motif : une cible qui disparaît sans
            # trace se fait redécouvrir au run suivant, puis réévaluer, puis
            # parfois repasser.
            ecartes.append({'name': c['name'][:160], 'website': c['base'], 'motif': scored['category_reason']})
            continue
        if not keeps_candidate(scored):
            continue
        results.append({
            'name': c['name'][:160],
            'website': c['base'],
            'origin': ORIGIN_WEB,
            'score': scored['score'],
            'raw_score': scored['raw_score'],
            'stack': scored['stack'],
            'emails': scored['emails'],
            'contact_urls': scored['contact_urls'],
            'reasons': scored['reasons'],
            'signals': scored['signals'],
            'family_scores': scored['family_scores'],
            'sources': sorted(c['sources'])[:6],
            'fetched_pages': fetched[:7],
            'snippet': text[:700],
            'zone_match': scored['zone_match'],
            'zone_term': scored['zone_term'],
            'category': scored['category'],
            'category_reason': scored['category_reason'],
            'category_evidence': scored['category_evidence'],
            'page_texts': pages[:4],
        })
        time.sleep(0.2)

    # Le registre apporte des candidats locaux que les moteurs ne montrent pas.
    # Il n'apporte ni verdict d'activité ni site : ces deux-là restent au crawl.
    registry_rows, registry_warnings = ([], ['registre désactivé (--no-registry)'])
    if '--no-registry' not in args:
        registry_rows, registry_warnings = registry_candidates(zone_key)
    for warning in registry_warnings:
        print(f'WARN: {warning}', file=sys.stderr)

    # Registre, crawl et CSV versionné alimentent le même payload. Une adresse
    # relevée à la main prévaut sur une extraction automatique du même domaine.
    results = merge_curated_agencies(results + registry_rows, zone_key)

    # Zone : tier1 d'abord, puis tier2 ; les hors-zone sont écartés si la zone
    # a déjà produit assez de résultats (>= 10), sinon gardés en réserve.
    zone_rank = {'tier1': 0, 'tier2': 1, 'none': 2}
    n_tier = sum(1 for r in results if r['zone_match'] != 'none')
    n_none = len(results) - n_tier
    zone_dropped = 0
    dropped_hors_zone = []
    if n_tier >= 10 and n_none:
        # Les écartés ne disparaissent pas sans trace : une piste hors des
        # termes de zone reste listée dans le payload et le rapport.
        dropped_hors_zone = [
            {'name': r['name'], 'website': r['website'], 'score': r['score']}
            for r in results if r['zone_match'] == 'none'
        ]
        results = [r for r in results if r['zone_match'] != 'none']
        zone_dropped = n_none
    results=sorted(results, key=lambda r: (-zone_rank.get(r['zone_match'], 2), r['score'], len(r['stack']), bool(r['emails'] or r['contact_urls'])), reverse=True)
    # Distance depuis l'adresse de référence de Cundo (--no-distance pour sauter).
    if '--no-distance' in args:
        origin_coords = ''
        for agency in results:
            agency.setdefault('address', None)
            agency.setdefault('postal_code', None)
            agency.setdefault('address_source', None)
            agency.setdefault('distance_m', None)
            agency['how'] = address_how(agency)
    else:
        # Le cache est chargé une fois, partagé par toute la passe, puis réécrit :
        # deux runs sur les mêmes adresses ne redemandent rien au géocodeur.
        geocode_cache = load_geocode_cache()
        origin_coords = enrich_with_distances(results, geocode_cache)
        save_geocode_cache(geocode_cache)
        for agency in results:
            agency['how'] = address_how(agency)
    radius_report = None
    if radius_m is not None:
        buckets = partition_by_radius(results, radius_m)
        radius_report = {
            'radius_m': radius_m,
            'origin_query': ORIGIN_ADDRESS,
            'inside': len(buckets['inside']),
            'approximate': len(buckets['approximate']),
            'outside': len(buckets['outside']),
            'unknown': len(buckets['unknown']),
            # Les écartés restent nommés : « rien dans le rayon » doit pouvoir se
            # relire comme « ces N-là étaient trop loin », pas comme un vide.
            'outside_radius': [
                {'name': a['name'], 'website': a['website'], 'dist_m': a['distance_m'], 'how': a['how']}
                for a in buckets['outside']
            ],
            'approximate_position': [
                {'name': a['name'], 'website': a['website'], 'dist_m': a['distance_m'], 'how': a['how']}
                for a in buckets['approximate']
            ],
            'unknown_position': [
                {'name': a['name'], 'website': a['website']} for a in buckets['unknown']
            ],
        }
        results = buckets['inside']
    ts=datetime.now().strftime('%Y%m%d-%H%M%S')
    payload={
        'ok': True,
        'version': 'v2',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'total': len(results),
        'scanned_domains': scanned,
        'seed_count': len(seeds),
        'queries': queries,
        'zone': zone_key,
        'zone_label': zone['label'],
        'distance_origin': ORIGIN_ADDRESS if origin_coords else None,
        'zone_stats': {
            'tier1': sum(1 for r in results if r['zone_match'] == 'tier1'),
            'tier2': sum(1 for r in results if r['zone_match'] == 'tier2'),
            'hors_zone_gardes': sum(1 for r in results if r['zone_match'] == 'none'),
            'hors_zone_ecartes': zone_dropped,
        },
        'hors_zone_ecartes_details': dropped_hors_zone,
        'radius': radius_report,
        # Ce que le registre a apporté, et ce qui l'a empêché d'apporter quoi que
        # ce soit. Un compteur à 0 sans avertissement ne se distinguerait pas
        # d'une zone réellement vide.
        'registry': {
            'candidates': len(registry_rows),
            'warnings': registry_warnings,
        },
        'origin_stats': {
            origin: sum(1 for r in results if origin in r.get('origins', []))
            for origin in (ORIGIN_CSV, ORIGIN_REGISTRY, ORIGIN_WEB)
        },
        'ecartes': ecartes,
        'agencies': results,
    }
    json_path=out_dir/f'agences-web-v2-{ts}.json'
    md_path=out_dir/f'agences-web-v2-{ts}.md'
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    if results:
        (DATA_DIR/'agencies_cache.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
        (FRONT_DIR/'latest.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    lines=[
        f'# 🏢 Prospection agences web V2 — {datetime.now().strftime("%d/%m/%Y %H:%M")}', '',
        f'- Seeds collectés : {len(seeds)}', f'- Domaines scannés : {scanned}', f'- Agences/studios retenus : {len(results)}',
        f'- Zone : {zone["label"]}',
        f'- Candidats du registre : {len(registry_rows)}',
        '',
    ]
    if registry_warnings:
        lines += ['> Registre : ' + ' · '.join(registry_warnings), '']
    if radius_report:
        lines += [
            f'- Rayon : {radius_report["radius_m"]} m depuis {radius_report["origin_query"]}',
            f'- Dans le rayon (adresse lue) : {radius_report["inside"]}'
            f' · position approximative : {radius_report["approximate"]}'
            f' · hors rayon : {radius_report["outside"]}'
            f' · position inconnue : {radius_report["unknown"]}',
            '',
        ]
    lines.append('## Top agences/studios & organismes de formation')
    for i,r in enumerate(results[:60],1):
        lines += [
            '', f'### {i}. {r["name"]}', '', f'- Score : {r["score"]}', f'- Site : {r["website"]}',
            f'- Stack détectée : {", ".join(r["stack"]) if r["stack"] else "à vérifier"}',
            f'- Emails : {", ".join(r["emails"]) if r["emails"] else "non détecté"}',
            f'- Contacts/recrutement : {", ".join(r["contact_urls"][:3]) if r["contact_urls"] else "non détecté"}',
            f'- Sources : {", ".join(r["sources"])}',
            f'- Pages lues : {", ".join(r["fetched_pages"][:4]) if r["fetched_pages"] else "aucune"}',
            f'- Type : {r.get("category","agence")} — {r.get("category_reason") or "motif non renseigné"}',
            f'- Identité : {r.get("identity_match") or "aucun identifiant"}'
            f' (SIREN {r.get("siren") or "inconnu"}, sources {", ".join(r.get("origins", [])) or "n/a"})',
            f'- Distance : {fmt_distance(r.get("distance_m"))} — adresse : {r.get("address") or "non publiée sur le site"} ({r.get("address_source") or "n/a"})',
            f'- Raisons : {"; ".join(r["reasons"][:9]) if r["reasons"] else "à qualifier"}',
            f'- Zone : {r["zone_match"]} ({r["zone_term"]})' if r['zone_match'] != 'none' else '- Zone : hors zone (réserve)',
        ]
    if ecartes:
        lines += ['', '## Écartés à la qualification', '']
        for r in ecartes:
            lines.append(f'- {r["name"]} — {r["website"]} ({r["motif"]})')
    if dropped_hors_zone:
        lines += ['', '## Écartés hors zone', '']
        for r in dropped_hors_zone:
            lines.append(f'- {r["name"]} — {r["website"]} (score {r["score"]})')
    if radius_report:
        for heading, key in (
            ('Position approximative (centre d’arrondissement, pas une adresse)', 'approximate_position'),
            ('Hors rayon', 'outside_radius'),
        ):
            if radius_report[key]:
                lines += ['', f'## {heading}', '']
                for r in radius_report[key]:
                    lines.append(f'- {r["name"]} — {r["website"]} ({fmt_distance(r["dist_m"])}, {r["how"]})')
        if radius_report['unknown_position']:
            lines += ['', '## Position inconnue (aucune adresse publiée trouvée)', '']
            for r in radius_report['unknown_position']:
                lines.append(f'- {r["name"]} — {r["website"]}')
    md_path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    if radius_report and not results:
        # latest.json n'est pas écrasé quand il n'y a rien (le garde `if results`
        # ci-dessus) : le dire, sinon le dashboard affiche l'ancienne passe et on
        # croit que le rayon a trouvé ces agences-là.
        print(
            f"Aucune agence avec adresse lue dans {radius_m} m : latest.json inchangé. "
            f"Détail dans {json_path}.",
            file=sys.stderr,
        )
    print(json.dumps({'ok': True, 'version':'v2', 'zone': zone_key, 'zone_label': zone['label'], 'radius': radius_report and {k: v for k, v in radius_report.items() if not isinstance(v, list)}, 'total': len(results), 'scanned_domains': scanned, 'seed_count': len(seeds), 'md': str(md_path), 'json': str(json_path), 'front': str(FRONT_DIR/'latest.json'), 'top': results[:10]}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    run()
