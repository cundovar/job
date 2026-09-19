import fs from 'fs';
import path from 'path';
import { spawn } from 'child_process';
import { PROJECT_ROOT } from '../config.js';

const PYTHON_BIN = 'python3.10';
const COMPANY_TOP_TIMEOUT = 240000; // 4 min
const COMPANY_PREPARE_TIMEOUT = 420000; // 7 min

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

function appendToCSV(csvPath, agencyName, domain) {
  const line = `${escapeCSVField(agencyName)},https://${domain},,agence_com_engagee,a_qualifier,\n`;

  // Ajoute en-tête si le fichier n'existe pas
  if (!fs.existsSync(csvPath)) {
    fs.writeFileSync(csvPath, 'nom,site,ville,type,statut,poste_vise\n', 'utf-8');
  }

  fs.appendFileSync(csvPath, line, 'utf-8');
}

function appendToYAML(yamlPath, agencyName, domain) {
  const today = new Date().toISOString().slice(0, 10);
  const yamlName = `"${String(agencyName).replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`;
  const entry = `  - nom: ${yamlName}
    type: agence_com_engagee
    zone: Ile-de-France
    taille_estimee: null
    taille_verifiee: false
    statut: a_qualifier
    notes: "Ajoutée le ${today} via bouton front (découverte Étape 0). URL: https://${domain}. Type et taille non confirmés."
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

    // Check pour une ligne de refus (-. Nom : REFUS. motif)
    const refusalMatch = trimmed.match(/^-\.\s+(.+?)\s*:\s*REFUS\.\s*(.+)$/);
    if (refusalMatch) {
      const [, name, msg] = refusalMatch;
      if (name.toLowerCase().includes(targetName.toLowerCase()) ||
          targetName.toLowerCase().includes(name.toLowerCase())) {
        reason = msg;
        foundTarget = true;
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
  prepareAgency
};
