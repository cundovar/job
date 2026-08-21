/**
 * config.js — Centralise les constantes de configuration du serveur.
 * Modifie ce fichier pour adapter les chemins ou le port selon l'environnement.
 */

import { fileURLToPath } from 'url';
import path from 'path';

// Reconstruit __dirname (pas disponible en ESM)
const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** Racine du projet job-search-automation-package */
export const PROJECT_ROOT = path.resolve(__dirname, '..');

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
