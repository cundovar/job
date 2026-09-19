/**
 * config.js — Centralise les constantes de configuration du serveur.
 * Modifie ce fichier pour adapter les chemins ou le port selon l'environnement.
 */

import { fileURLToPath } from 'url';
import path from 'path';
import fs from 'fs';

// Reconstruit __dirname (pas disponible en ESM)
const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** Racine du projet job-search-automation-package */
export const PROJECT_ROOT = path.resolve(__dirname, '..');

/**
 * Charge le `.env` racine dans process.env (pas de dotenv dans les
 * dépendances du serveur). N'écrase jamais une variable déjà définie par
 * l'environnement d'exécution (Docker/Coolify).
 */
function loadRootEnv() {
  const envPath = path.join(PROJECT_ROOT, '.env');
  if (!fs.existsSync(envPath)) return;
  const content = fs.readFileSync(envPath, 'utf-8');
  for (const line of content.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eq = trimmed.indexOf('=');
    if (eq === -1) continue;
    const key = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (key && !(key in process.env)) {
      process.env[key] = value;
    }
  }
}

loadRootEnv();

/** Port d'écoute du serveur Express */
export const PORT = process.env.PORT || 3001;

/**
 * Chemin vers le fichier des candidatures préparées (LECTURE SEULE).
 * Ce fichier est généré par le pipeline Python, on ne l'écrit jamais côté serveur.
 */
export const CANDIDATURES_PATH = path.resolve(
  __dirname,
  '../front/public/data/candidatures.json'
);

/**
 * Chemin vers le fichier tracker partagé avec le cron Python.
 * Format : { [id]: { status, applied_at, follow_up_at, ... } }
 * Ne pas changer ce format sans mettre à jour le cron Python.
 */
export const TRACKER_PATH = path.resolve(
  __dirname,
  '../data/applications_tracker.json'
);
