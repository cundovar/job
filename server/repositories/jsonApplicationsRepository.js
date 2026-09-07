/**
 * jsonApplicationsRepository.js — Implémentation JSON du repository.
 *
 * Lit les candidatures depuis front/public/data/candidatures.json (jamais modifié).
 * Stocke les statuts "postulé" dans data/applications_tracker.json,
 * au MÊME format que le tracker Python (compatibilité cron relances).
 */

import fs from 'fs';
import path from 'path';
import { spawn } from 'child_process';
import ApplicationsRepository from './applicationsRepository.js';
import { CANDIDATURES_PATH, TRACKER_PATH, PROJECT_ROOT } from '../config.js';

const PREPARE_PYTHON_BIN = process.env.CV_PYTHON_BIN || 'python3';
const PREPARE_MAX_OUTPUT = 10 * 1024 * 1024;
const PREPARE_KILL_GRACE_MS = 5000;
const PREPARE_TIMEOUT_MS = Number.parseInt(
  process.env.PREPARE_TASK_TIMEOUT_MS || String(10 * 60 * 1000),
  10
);

/**
 * Lance le script Python de preparation SANS bloquer la boucle d'evenements.
 *
 * spawnSync gelait tout le process Node pendant les 20-40 s du script : aucune
 * autre requete n'etait servie (health, polling CV...) et les clients mobiles
 * perdaient la connexion avant la reponse. On passe donc en spawn asynchrone.
 */
function runPreparePython(job) {
  return new Promise((resolve, reject) => {
    const child = spawn(
      PREPARE_PYTHON_BIN,
      ['-m', 'hermes_commands.job_prepare_payload'],
      { cwd: PROJECT_ROOT, stdio: ['pipe', 'pipe', 'pipe'] }
    );

    let stdout = '';
    let stderr = '';
    let outputBytes = 0;
    let outputExceeded = false;
    let timedOut = false;
    let forceKillTimer = null;

    const collect = (target, chunk) => {
      outputBytes += chunk.length;
      if (outputBytes > PREPARE_MAX_OUTPUT) {
        outputExceeded = true;
        child.kill('SIGTERM');
        return target;
      }
      return target + chunk.toString('utf-8');
    };

    child.stdout.on('data', chunk => { stdout = collect(stdout, chunk); });
    child.stderr.on('data', chunk => { stderr = collect(stderr, chunk); });

    const timer = setTimeout(() => {
      timedOut = true;
      child.kill('SIGTERM');
      forceKillTimer = setTimeout(() => child.kill('SIGKILL'), PREPARE_KILL_GRACE_MS);
      forceKillTimer.unref();
    }, PREPARE_TIMEOUT_MS);
    timer.unref();

    const clearTimers = () => {
      clearTimeout(timer);
      if (forceKillTimer) clearTimeout(forceKillTimer);
    };

    child.on('error', err => {
      clearTimers();
      reject(new Error(`Preparation impossible : ${err.message}`));
    });

    child.on('close', code => {
      clearTimers();
      if (timedOut) {
        reject(new Error('La preparation de la candidature a depasse le delai maximal.'));
        return;
      }
      if (outputExceeded) {
        reject(new Error('La sortie du script de preparation depasse la limite autorisee.'));
        return;
      }
      if (code !== 0) {
        const details = (stderr || stdout || `code ${code}`).trim();
        reject(new Error(`Preparation impossible : ${details}`));
        return;
      }
      resolve(stdout);
    });

    child.stdin.on('error', () => {});
    child.stdin.end(JSON.stringify({ job }));
  });
}

export default class JsonApplicationsRepository extends ApplicationsRepository {
  // ─── Lecture / écriture du tracker JSON ───────────────────────────────────

  /** Charge le tracker depuis le disque. Retourne {} si absent ou corrompu. */
  _loadTracker() {
    try {
      if (!fs.existsSync(TRACKER_PATH)) return {};
      const raw = fs.readFileSync(TRACKER_PATH, 'utf-8').trim();
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      return typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
    } catch {
      return {};
    }
  }

  /** Sauvegarde le tracker sur le disque. Crée le dossier data/ si absent. */
  _saveTracker(records) {
    const dir = path.dirname(TRACKER_PATH);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(TRACKER_PATH, JSON.stringify(records, null, 2), 'utf-8');
  }

  /** Charge la liste des candidatures préparées (lecture seule). */
  _loadCandidatures() {
    try {
      const raw = fs.readFileSync(CANDIDATURES_PATH, 'utf-8');
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed.candidatures) ? parsed.candidatures : [];
    } catch {
      return [];
    }
  }

  // ─── Fusion candidature + statut ──────────────────────────────────────────

  /** Enrichit un objet candidature avec son statut issu du tracker. */
  _merge(candidature, tracker) {
    const record = tracker[candidature.id];
    if (record && record.status === 'applied') {
      return {
        ...candidature,
        status: 'applied',
        applied_at: record.applied_at || null,
        follow_up_at: record.follow_up_at || null,
      };
    }
    return {
      ...candidature,
      status: 'ready_to_apply',
      applied_at: null,
      follow_up_at: null,
    };
  }

  // ─── Interface publique ────────────────────────────────────────────────────

  async getAll() {
    const candidatures = this._loadCandidatures();
    const tracker = this._loadTracker();
    return candidatures.map(c => this._merge(c, tracker));
  }

  async getById(id) {
    const candidatures = this._loadCandidatures();
    const c = candidatures.find(x => x.id === id);
    if (!c) return null;
    const tracker = this._loadTracker();
    return this._merge(c, tracker);
  }

  async prepareFromJob(job) {
    if (!job || typeof job !== 'object') {
      throw new Error('Offre invalide');
    }
    if (!job.title && !job.url) {
      throw new Error('Offre invalide : titre ou URL requis');
    }

    const stdout = await runPreparePython(job);

    let prepared;
    try {
      prepared = JSON.parse(stdout);
    } catch {
      throw new Error(`Réponse préparation invalide : ${stdout}`);
    }

    const candidature = await this.getById(prepared.id);
    return { ...prepared, candidature };
  }

  async markApplied(id) {
    // Vérifie que la candidature existe
    const candidature = await this.getById(id);
    if (!candidature) throw new Error(`Candidature introuvable : ${id}`);

    const tracker = this._loadTracker();
    const now = new Date();

    // Calcule les dates au format YYYY-MM-DD (comme le tracker Python)
    const appliedAt = now.toISOString().slice(0, 10);
    const followUpAt = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000)
      .toISOString()
      .slice(0, 10);

    const existing = tracker[id] || {};
    const record = {
      ...existing,
      key: id,
      status: 'applied',
      job_title: candidature.poste || '',
      company: candidature.entreprise || '',
      applied_at: appliedAt,
      follow_up_at: followUpAt,
      updated_at: now.toISOString(),
    };
    // Conserve created_at si déjà présent
    if (!record.created_at) record.created_at = now.toISOString();

    tracker[id] = record;
    this._saveTracker(tracker);

    return { ...candidature, ...record };
  }

  async markNotApplied(id) {
    const candidature = await this.getById(id);
    if (!candidature) throw new Error(`Candidature introuvable : ${id}`);

    const tracker = this._loadTracker();
    // Supprime l'entrée pour annuler le statut "applied"
    delete tracker[id];
    this._saveTracker(tracker);

    return { ...candidature, status: 'ready_to_apply', applied_at: null, follow_up_at: null };
  }
}
