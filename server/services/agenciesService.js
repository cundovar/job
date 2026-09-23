import fs from 'fs';
import path from 'path';
import { spawn } from 'child_process';
import { PROJECT_ROOT } from '../config.js';

const PYTHON_BIN = process.env.PYTHON_BIN || 'python3';
const COMPANY_TOP_TIMEOUT = 240000; // 4 min

// ── Historique par recherche (phase 3) ────────────────────────────────────
// `tools/agency_prospecting_v2.py` est le seul producteur de ces fichiers ; le
// serveur ne fait que les lire. `latest.json` reste l'alias de compatibilité :
// une installation antérieure à l'index continue de fonctionner sans sélecteur.
const AGENCIES_DIR = path.join(PROJECT_ROOT, 'front/public/data/agencies');
const SEARCHES_DIR = path.join(AGENCIES_DIR, 'searches');
const SEARCH_INDEX_PATH = path.join(AGENCIES_DIR, 'index.json');
const LATEST_PATH = path.join(AGENCIES_DIR, 'latest.json');
const ANALYSES_PATH = path.join(PROJECT_ROOT, 'data/agency_analyses.json');

// Identifiant produit par make_search_id : `<zone-slug>-<AAAAMMJJ-HHMMSS>`.
// Le motif interdit `/` et `..` ; l'appartenance à l'index est vérifiée en plus,
// pour qu'un identifiant bien formé mais inconnu ne devienne pas un chemin.
const SEARCH_ID_PATTERN = /^[a-z0-9][a-z0-9._-]{0,79}$/;
const LATEST_SEARCH_ID = 'latest';
const COMPANY_PREPARE_TIMEOUT = Number.parseInt(
  process.env.COMPANY_PREPARE_TIMEOUT_MS || String(20 * 60 * 1000),
  10
);

function normalizeDomain(domain) {
  if (!domain || typeof domain !== 'string') return null;
  let normalized = domain.toLowerCase().trim();

  // Supprimer protocole
  normalized = normalized.replace(/^https?:\/\//, '');

  // Supprimer www et les parties après le TLD (chemin, query, etc.)
  normalized = normalized.replace(/^www\./, '');
  normalized = normalized.split('/')[0];
  normalized = normalized.split('?')[0];

  return normalized || null;
}

function domainMatchesAgency(domain, agency) {
  if (!agency.website) return false;
  const agencyDomain = normalizeDomain(agency.website);
  return agencyDomain === domain;
}

function validateDomain(domain) {
  if (!domain || typeof domain !== 'string') return false;
  const normalized = normalizeDomain(domain);
  if (!normalized) return false;
  // Simple check : au moins un point et pas d'espaces
  return normalized.includes('.') && !normalized.includes(' ');
}

const GENERIC_NAMES = new Set([
  'voir', 'accueil', 'home', 'menu', 'plus', 'ici', 'site',
  'agence', 'contact', 'recherche', 'le site', 'notre agence',
]);

// Le scraper attrape parfois un texte de menu (« Voir ») comme nom.
// On retombe sur le domaine : amphibee.fr → « Amphibee ».
function cleanAgencyName(name, domain) {
  const n = (name || '').trim();
  const isJunk = !n || n.length < 4 || GENERIC_NAMES.has(n.toLowerCase());
  if (!isJunk) return n;
  const base = (domain || '').replace(/^www\./, '').split('.')[0];
  return base ? base.charAt(0).toUpperCase() + base.slice(1) : (n || 'Agence');
}

function isAlreadyTargeted(domain, csvPath) {
  if (!fs.existsSync(csvPath)) return false;
  const content = fs.readFileSync(csvPath, 'utf-8');
  const lines = content.split('\n').filter(l => l.trim());

  for (const line of lines) {
    // Saute l'en-tête
    if (line.startsWith('nom,')) continue;

    // Extraction simple du domaine depuis la colonne site (2ème colonne)
    const parts = parseCSVLine(line);
    if (parts[1]) {
      const siteDomain = normalizeDomain(parts[1]);
      if (siteDomain === domain) return true;
    }
  }

  return false;
}

function parseCSVLine(line) {
  // Parsing CSV simple : gère les guillemets et virgules
  const result = [];
  let current = '';
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    const nextChar = line[i + 1];

    if (char === '"') {
      if (inQuotes && nextChar === '"') {
        current += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === ',' && !inQuotes) {
      result.push(current.trim());
      current = '';
    } else {
      current += char;
    }
  }

  result.push(current.trim());
  return result;
}

function escapeCSVField(field) {
  if (!field) return '""';
  const str = String(field);
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

// Colonnes de config/companies.csv, dans l'ordre — 9 depuis que `siren` existe.
// `adresse`, `code_postal` et `siren` restent vides : une agence ajoutée depuis
// un domaine n'a ni adresse relevée ni immatriculation confirmée, et les déduire
// du nom de domaine serait les inventer. Écrire moins de champs que l'en-tête
// décalerait toutes les colonnes à la relecture.
const CSV_HEADER = 'nom,site,ville,type,statut,poste_vise,adresse,code_postal,siren';

function appendToCSV(csvPath, agencyName, domain, options = {}) {
  // Colonnes : nom,site,ville,type,statut,poste_vise,adresse,code_postal,siren
  const ville = '';
  // Le scout sait si la structure est une organisme de formation
  // (options.type = formation_organisation) : c'est ce type qui choisit le
  // poste visé (poste_vise_par_type) donc l'angle lettre/mail/CV.
  const type = options.type || 'agence_com_engagee';
  const statut = options.statut || 'a_qualifier';
  const poste = '';
  const adresse = options.adresse ? escapeCSVField(options.adresse) : '';
  const codePostal = options.codePostal || '';
  // Site : l'URL relevée par le scout (options.site) fait foi — la reconstruire
  // depuis le domaine normalisé perd le « www », et un certificat TLS qui ne
  // couvre pas le domaine nu fait alors échouer la mesure en « site injoignable
  // SSLError hostname mismatch » (cas 10MentionWeb, 23/09/2026).
  const site = (options.site || `https://${domain}`).replace(/\/+$/, '');
  const line = `${escapeCSVField(agencyName)},${site},${ville},${type},${statut},${poste},${adresse},${codePostal},\n`;

  // Ajoute en-tête si le fichier n'existe pas
  if (!fs.existsSync(csvPath)) {
    fs.writeFileSync(csvPath, `${CSV_HEADER}\n`, 'utf-8');
  }

  fs.appendFileSync(csvPath, line, 'utf-8');
}

function appendToYAML(yamlPath, agencyName, domain, options = {}) {
  const today = new Date().toISOString().slice(0, 10);
  const yamlName = `"${String(agencyName).replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`;
  const statut = options.statut || 'a_qualifier';
  // Même règle que appendToCSV : l'URL du scout (avec www) fait foi.
  const site = (options.site || `https://${domain}`).replace(/\/+$/, '');
  const notes = options.statut
    ? `Ajoutée le ${today} via Agency Scout (bouton Retenir & préparer). URL: ${site}. Adresse Google: ${options.adresse || 'n/a'}. Statut retenue : préparation lancée, registre/SIREN à confirmer.`
    : `Ajoutée le ${today} via bouton front (découverte Étape 0). URL: ${site}. Type et taille non confirmés.`;
  const entry = `  - nom: ${yamlName}
    type: ${options.type || 'agence_com_engagee'}
    zone: Ile-de-France
    taille_estimee: null
    taille_verifiee: false
    statut: ${statut}
    notes: "${notes}"
`;

  // Ajoute avant la fermeture du fichier ou après les autres entrées
  let content = fs.readFileSync(yamlPath, 'utf-8');

  // Cherche la dernière ligne qui n'est pas vide et n'est pas un commentaire
  const lines = content.split('\n');
  let insertIdx = lines.length - 1;

  while (insertIdx >= 0 && (!lines[insertIdx].trim() || lines[insertIdx].trim().startsWith('#'))) {
    insertIdx--;
  }

  // Insère après la dernière ligne de contenu
  if (insertIdx >= 0) {
    lines.splice(insertIdx + 1, 0, entry);
    content = lines.join('\n');
  } else {
    content += entry;
  }

  fs.writeFileSync(yamlPath, content, 'utf-8');
}

async function runPython(args, timeout = 60000) {
  return new Promise((resolve, reject) => {
    const child = spawn(PYTHON_BIN, args, {
      cwd: PROJECT_ROOT,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    let stdout = '';
    let stderr = '';
    let timedOut = false;

    child.stdout.on('data', chunk => {
      stdout += chunk.toString('utf-8');
    });

    child.stderr.on('data', chunk => {
      stderr += chunk.toString('utf-8');
    });

    const timer = setTimeout(() => {
      timedOut = true;
      child.kill('SIGTERM');
    }, timeout);

    child.on('close', code => {
      clearTimeout(timer);

      if (timedOut) {
        reject(new Error(`Process timeout (${timeout}ms)`));
      } else if (code !== 0) {
        reject(new Error(`Process exited with code ${code}: ${stderr}`));
      } else {
        resolve(stdout);
      }
    });

    child.on('error', err => {
      clearTimeout(timer);
      reject(err);
    });
  });
}

function parseCompanyTopOutput(output, targetName) {
  // Format :
  // 1. Agence LIMITE
  //    Poste vise : Développeur web / Intégrateur
  //    URL : https://agence-limite.fr
  //    Constats confirmes : 3
  //    - constat 1
  //    - constat 2
  //
  // -. Entreprise REFUSÉE : REFUS. motif

  const lines = output.split('\n');
  let number = null;
  let constats = 0;
  let reason = null;
  let foundTarget = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // Check pour une ligne de numéro (N. Nom ou -. Nom : REFUS.)
    const numberMatch = trimmed.match(/^(\d+)\.\s+(.+)$/);
    if (numberMatch) {
      const [, num, name] = numberMatch;
      // Normalisez le nom pour la comparaison
      if (name.toLowerCase().includes(targetName.toLowerCase()) ||
          targetName.toLowerCase().includes(name.toLowerCase())) {
        number = parseInt(num, 10);
        foundTarget = true;
        // Compte les constats sur les lignes suivantes
        let j = i + 1;
        while (j < lines.length) {
          const nextLine = lines[j].trim();
          if (nextLine.startsWith('- ')) {
            constats++;
            j++;
          } else if (nextLine.match(/^\d+\./)) {
            break; // Prochaine entreprise
          } else if (nextLine.startsWith('-. ') || nextLine === '') {
            break;
          } else {
            j++;
          }
        }
        break;
      }
    }

    // Check pour une ligne de refus. Format actuel de company_top (motif sur
    // la ligne suivante) :
    //   -. Nom : REFUS
    //      Motif : raison
    // L'ancien format inline « -. Nom : REFUS. raison » reste accepté.
    const refusalMatch = trimmed.match(/^-\.\s+(.+?)\s*:\s*REFUS\b\.?\s*(.*)$/);
    if (refusalMatch) {
      const [, name, inlineMsg] = refusalMatch;
      if (name.toLowerCase().includes(targetName.toLowerCase()) ||
          targetName.toLowerCase().includes(name.toLowerCase())) {
        foundTarget = true;
        reason = (inlineMsg || '').trim() || null;
        if (!reason) {
          // Le motif vit sur la ligne suivante (« Motif : … »)
          for (let j = i + 1; j < lines.length; j++) {
            const motifLine = lines[j].trim();
            if (!motifLine) break;
            const motifMatch = motifLine.match(/^Motif\s*:\s*(.+)$/i);
            if (motifMatch) {
              reason = motifMatch[1].trim();
            }
            break;
          }
        }
        break;
      }
    }
  }

  return { number, constats, reason, foundTarget };
}

async function measureAgency(agencyName, dry = false) {
  try {
    const output = await runPython(
      ['-m', 'hermes_commands.company_top', '--refresh'],
      COMPANY_TOP_TIMEOUT
    );

    const result = parseCompanyTopOutput(output, agencyName);

    if (!result.foundTarget) {
      return {
        ok: false,
        stage: 'mesure',
        error: `Agence ${agencyName} non trouvée ou identifiant invalide`
      };
    }

    if (result.reason) {
      return {
        ok: false,
        stage: 'mesure',
        reason: result.reason
      };
    }

    if (!result.number) {
      return {
        ok: false,
        stage: 'mesure',
        error: `Impossible d'extraire le numéro de l'agence ${agencyName}`
      };
    }

    return { ok: true, number: result.number, constats: result.constats };
  } catch (err) {
    return {
      ok: false,
      stage: 'mesure',
      error: err.message
    };
  }
}

async function prepareAgency(number, agencyName, dry = false) {
  try {
    const output = await runPython(
      ['-m', 'hermes_commands.company_prepare', String(number)],
      COMPANY_PREPARE_TIMEOUT
    );

    // Vérifie que candidatures.json contient une entrée correspondante
    const candidaturesPath = path.join(PROJECT_ROOT, 'front/public/data/candidatures.json');
    if (!fs.existsSync(candidaturesPath)) {
      return {
        ok: false,
        stage: 'préparation',
        error: 'Fichier candidatures.json non trouvé'
      };
    }

    const candidatures = JSON.parse(fs.readFileSync(candidaturesPath, 'utf-8'));
    const entry = (candidatures.candidatures || []).find(c =>
      c.entreprise && c.entreprise.toLowerCase().includes(agencyName.toLowerCase())
    );

    if (!entry) {
      return {
        ok: false,
        stage: 'préparation',
        error: 'Dossier créé mais non trouvé dans candidatures.json'
      };
    }

    // `preuves` est un dict { url, mission, adresse, adresse_source, contact } —
    // sa simple présence distingue un dossier de prospection (même règle que le front).
    if (!entry.preuves || Object.keys(entry.preuves).length === 0) {
      return {
        ok: false,
        stage: 'préparation',
        error: 'Dossier créé sans preuves suffisantes'
      };
    }

    return { ok: true };
  } catch (err) {
    return {
      ok: false,
      stage: 'préparation',
      error: err.message
    };
  }
}

// Une passe de prospection crawle des dizaines de domaines et géocode chaque
// adresse (Nominatim impose ~1,1 s entre deux appels) : compter en minutes, pas
// en secondes. D'où la file asynchrone plutôt qu'une requête HTTP maintenue.
const PROSPECTING_TIMEOUT = Number.parseInt(
  process.env.AGENCY_PROSPECTING_TIMEOUT_MS || String(30 * 60 * 1000),
  10
);

const ZONE_PATTERN = /^[a-z0-9-]{1,40}$/;
// Un nom de commune, pas une expression libre : lettres accentuées, espaces,
// apostrophes et traits d'union. Ce qui n'entre pas ici n'a pas à devenir un
// argument de ligne de commande.
const CITY_PATTERN = /^[\p{L}][\p{L}\s'’.-]{1,59}$/u;
const DEPARTEMENT_PATTERN = /^(2[AB]|\d{2,3})$/i;

function sameProspectingRequest(task, { zone, city, departement, radiusM }) {
  const requestedRadius = radiusM == null ? null : Number(radiusM);
  const taskRadius = task?.radius_m == null ? null : Number(task.radius_m);
  // La ville fait partie de l'identité de la demande : sans elle, une recherche
  // « Lille » relancée pendant un run « Montreuil » recevrait le task_id de
  // Montreuil et lirait ses résultats en croyant lire les siens.
  return (
    (task?.zone || null) === (zone || null)
    && (task?.city || null) === (city || null)
    && (task?.departement || null) === (departement || null)
    && taskRadius === requestedRadius
  );
}

async function runProspecting({ zone = null, city = null, departement = null, radiusM = null } = {}) {
  const args = ['tools/agency_prospecting_v2.py'];
  if (city) {
    if (!CITY_PATTERN.test(city)) {
      throw new Error(`Ville invalide : ${city}`);
    }
    args.push('--ville', city);
    if (departement) {
      if (!DEPARTEMENT_PATTERN.test(departement)) {
        throw new Error(`Département invalide : ${departement}`);
      }
      args.push('--departement', String(departement).toUpperCase());
    }
  } else {
    // `zone` reste accepté pour les préréglages historiques, mais ce n'est plus
    // la voie recommandée : une ville se demande par son nom.
    const zoneKey = zone || 'ile-de-france';
    if (!ZONE_PATTERN.test(zoneKey)) {
      throw new Error(`Zone invalide : ${zoneKey}`);
    }
    args.push('--zone', zoneKey);
  }
  if (radiusM != null) {
    const radius = Number.parseInt(radiusM, 10);
    if (!Number.isInteger(radius) || radius <= 0) {
      throw new Error(`Rayon invalide : ${radiusM}`);
    }
    args.push('--radius', String(radius));
  }

  const output = await runPython(args, PROSPECTING_TIMEOUT);
  // Le script imprime son récapitulatif en JSON sur stdout, précédé de lignes de
  // progression. On repart du dernier objet complet plutôt que de tout parser.
  const start = output.indexOf('{');
  if (start === -1) {
    throw new Error(`Sortie de prospection illisible : ${output.trim().slice(-500)}`);
  }
  return JSON.parse(output.slice(start));
}

function readJsonFile(file) {
  if (!fs.existsSync(file)) return null;
  try {
    return JSON.parse(fs.readFileSync(file, 'utf-8'));
  } catch {
    return null;
  }
}

/**
 * Index des recherches. Quand il n'existe pas (installation antérieure à la
 * phase 3, ou clone neuf où seul `latest.json` est versionné), on en synthétise
 * un d'une seule entrée à partir de `latest.json` : le front garde alors son
 * comportement d'avant, sélecteur compris, sans afficher un historique vide qui
 * se relirait comme « aucune recherche n'a eu lieu ».
 */
function readSearchIndex() {
  const index = readJsonFile(SEARCH_INDEX_PATH);
  if (index && Array.isArray(index.searches) && index.searches.length > 0) {
    return { ...index, source: 'index' };
  }

  const latest = readJsonFile(LATEST_PATH);
  if (!latest) {
    return { version: 1, updated_at: null, latest_search_id: null, searches: [], source: 'vide' };
  }
  const searchId = latest.search_id || LATEST_SEARCH_ID;
  return {
    version: 1,
    updated_at: latest.generated_at || null,
    latest_search_id: searchId,
    source: 'latest',
    searches: [{
      search_id: searchId,
      zone: latest.zone || null,
      zone_label: latest.zone_label || null,
      generated_at: latest.generated_at || null,
      radius_m: latest.radius?.radius_m ?? null,
      origin: latest.distance_origin || null,
      total: (latest.agencies || []).length,
      state: 'ok',
      pinned: false,
      file: 'latest.json',
    }],
  };
}

function knownSearchIds() {
  return readSearchIndex().searches.map(search => search.search_id).filter(Boolean);
}

/**
 * Charge le payload d'une recherche. Un identifiant absent (ou `latest`) rend
 * l'alias de compatibilité ; un identifiant inconnu lève une erreur qui **nomme
 * les recherches connues** — un tableau vide se relirait comme « il n'y a rien »,
 * et c'est précisément la lecture qui a déjà conduit à inventer des agences.
 */
function readSearchPayload(searchId) {
  if (!searchId || searchId === LATEST_SEARCH_ID) {
    const latest = readJsonFile(LATEST_PATH);
    if (!latest) {
      throw new Error('Aucune recherche publiée : lance une prospection avant de cibler.');
    }
    return { payload: latest, search_id: latest.search_id || LATEST_SEARCH_ID, source: 'latest' };
  }

  const known = knownSearchIds();
  if (!SEARCH_ID_PATTERN.test(searchId) || !known.includes(searchId)) {
    throw new Error(
      `Recherche inconnue : « ${searchId} ». Recherches disponibles : ${known.join(', ') || 'aucune'}.`
    );
  }

  const file = path.join(SEARCHES_DIR, `${searchId}.json`);
  const payload = readJsonFile(file);
  if (payload) {
    return { payload, search_id: searchId, source: 'search' };
  }

  // Indexée mais introuvable sur le disque : c'est le cas de l'index synthétisé
  // depuis `latest.json`, où le fichier par recherche n'existe pas encore.
  const latest = readJsonFile(LATEST_PATH);
  if (latest && (latest.search_id || LATEST_SEARCH_ID) === searchId) {
    return { payload: latest, search_id: searchId, source: 'latest' };
  }
  throw new Error(`Recherche « ${searchId} » indexée mais son fichier est absent.`);
}

/**
 * Analyses persistées (`data/agency_analyses.json`), en lecture seule et
 * aplaties par domaine. Le fichier brut n'est jamais servi tel quel : son
 * `history` et ses empreintes n'ont pas à transiter vers le navigateur, et
 * aucune route ne l'écrit.
 */
function readPersistedAnalyses() {
  const cache = readJsonFile(ANALYSES_PATH);
  const entries = cache && typeof cache.analyses === 'object' ? cache.analyses : {};
  const analyses = {};
  for (const [domain, entry] of Object.entries(entries)) {
    if (!entry || typeof entry !== 'object') continue;
    const analysis = entry.analysis && typeof entry.analysis === 'object' ? entry.analysis : {};
    analyses[domain] = {
      domain,
      status: entry.status || analysis.fit_status || 'review',
      obsolete: entry.obsolete === true,
      analyzed_at: entry.analyzed_at || analysis.analyzed_at || null,
      provider: entry.provider || null,
      strengths: analysis.strengths || [],
      weaknesses: analysis.weaknesses || [],
      application_angle: analysis.application_angle || '',
      fit_summary: analysis.fit_summary || '',
      fit_score: analysis.fit_score ?? null,
      confidence: analysis.confidence || '',
      category: analysis.category || '',
      evidence_urls: analysis.evidence_urls || [],
      issues: analysis.issues || [],
    };
  }
  return { updated_at: cache?.updated_at || null, count: Object.keys(analyses).length, analyses };
}

export {
  normalizeDomain,
  validateDomain,
  domainMatchesAgency,
  cleanAgencyName,
  isAlreadyTargeted,
  appendToCSV,
  appendToYAML,
  runPython,
  parseCompanyTopOutput,
  measureAgency,
  prepareAgency,
  runProspecting,
  sameProspectingRequest,
  readSearchIndex,
  readSearchPayload,
  readPersistedAnalyses,
  knownSearchIds,
  LATEST_SEARCH_ID,
  SEARCH_ID_PATTERN
};
