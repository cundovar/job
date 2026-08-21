/**
 * jsonApplicationsRepository.js — Implémentation JSON du repository.
 *
 * Lit les candidatures depuis front/public/data/candidatures.json (jamais modifié).
 * Stocke les statuts "postulé" dans data/applications_tracker.json,
 * au MÊME format que le tracker Python (compatibilité cron relances).
 */

import fs from 'fs';
import path from 'path';
import { spawnSync } from 'child_process';
import ApplicationsRepository from './applicationsRepository.js';
import { CANDIDATURES_PATH, TRACKER_PATH, PROJECT_ROOT } from '../config.js';

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

    const result = spawnSync(
      'python3',
      ['-m', 'hermes_commands.job_prepare_payload'],
      {
        cwd: PROJECT_ROOT,
        input: JSON.stringify({ job }),
        encoding: 'utf-8',
        maxBuffer: 10 * 1024 * 1024,
      }
    );

    if (result.status !== 0) {
      const details = (result.stderr || result.stdout || 'Erreur inconnue').trim();
      throw new Error(`Préparation impossible : ${details}`);
    }

    let prepared;
    try {
      prepared = JSON.parse(result.stdout);
    } catch {
      throw new Error(`Réponse préparation invalide : ${result.stdout}`);
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
