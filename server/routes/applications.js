/**
 * routes/applications.js — Endpoints REST pour les candidatures.
 *
 * Les routes ne connaissent QUE l'interface du repository.
 * Elles ne savent pas si la donnée vient de JSON ou d'une BDD.
 *
 * @param {import('../repositories/applicationsRepository.js').default} repo
 */
import { Router } from 'express';
import fs from 'fs';
import path from 'path';
import { spawnSync } from 'child_process';
import { PROJECT_ROOT } from '../config.js';

const CV_FILES = new Set([
  'cv_adaptation_plan.json',
  'cv_draft.json',
  'cv_review.json',
  'cv_final_review.json',
  'cv_final.json',
  'cv_final.md',
  'cv_canva_copy.md',
  'cv_final.html',
  'cv_final.pdf',
]);

function applicationDir(id) {
  const base = path.resolve(PROJECT_ROOT, 'output/applications');
  const dir = path.resolve(base, id);
  if (!dir.startsWith(base + path.sep)) {
    throw new Error('Identifiant candidature invalide');
  }
  return dir;
}

function cvStatus(id) {
  const cvDir = path.join(applicationDir(id), 'cv');
  const files = {};
  for (const file of CV_FILES) {
    const filePath = path.join(cvDir, file);
    files[file] = fs.existsSync(filePath);
  }
  let review = null;
  const reviewPath = path.join(cvDir, 'cv_final_review.json');
  if (fs.existsSync(reviewPath)) {
    try {
      review = JSON.parse(fs.readFileSync(reviewPath, 'utf-8'));
    } catch {
      review = null;
    }
  }
  return { exists: fs.existsSync(cvDir), files, review };
}

export default function createApplicationsRouter(repo) {
  const router = Router();

  // GET /api/health — Vérifie que le serveur tourne
  router.get('/health', (_req, res) => {
    res.json({ ok: true });
  });

  // GET /api/applications — Liste toutes les candidatures avec leur statut
  router.get('/applications', async (_req, res) => {
    try {
      const applications = await repo.getAll();
      res.json(applications);
    } catch (err) {
      console.error('[GET /applications]', err.message);
      res.status(500).json({ error: 'Erreur lors de la récupération des candidatures' });
    }
  });

  // POST /api/applications/prepare — Génère une candidature depuis une offre de recherche
  router.post('/applications/prepare', async (req, res) => {
    try {
      const result = await repo.prepareFromJob(req.body?.job);
      res.status(201).json(result);
    } catch (err) {
      console.error('[POST /applications/prepare]', err.message);
      res.status(500).json({ error: err.message });
    }
  });

  // GET /api/applications/:id/cv/status — Vérifie si un CV personnalisé existe
  router.get('/applications/:id/cv/status', async (req, res) => {
    try {
      const dir = applicationDir(req.params.id);
      if (!fs.existsSync(dir)) return res.status(404).json({ error: `Dossier candidature introuvable : ${req.params.id}` });
      res.json(cvStatus(req.params.id));
    } catch (err) {
      console.error('[GET /applications/:id/cv/status]', err.message);
      res.status(400).json({ error: err.message });
    }
  });

  // POST /api/applications/:id/cv/prepare — Génère les fichiers CV personnalisés
  router.post('/applications/:id/cv/prepare', async (req, res) => {
    try {
      const dir = applicationDir(req.params.id);
      if (!fs.existsSync(dir)) return res.status(404).json({ error: `Dossier candidature introuvable : ${req.params.id}` });

      const result = spawnSync(
        'python3',
        ['-m', 'hermes_commands.cv_prepare', '--application-dir', dir],
        {
          cwd: PROJECT_ROOT,
          encoding: 'utf-8',
          maxBuffer: 10 * 1024 * 1024,
        }
      );

      if (result.status !== 0) {
        const details = (result.stderr || result.stdout || 'Erreur inconnue').trim();
        return res.status(500).json({ error: `Génération CV impossible : ${details}` });
      }

      let payload;
      try {
        payload = JSON.parse(result.stdout);
      } catch {
        return res.status(500).json({ error: `Réponse CV invalide : ${result.stdout}` });
      }
      res.status(201).json({ ...payload, status: cvStatus(req.params.id) });
    } catch (err) {
      console.error('[POST /applications/:id/cv/prepare]', err.message);
      res.status(400).json({ error: err.message });
    }
  });

  // GET /api/applications/:id/cv/download/:file — Télécharge un fichier CV généré
  router.get('/applications/:id/cv/download/:file', async (req, res) => {
    try {
      const dir = applicationDir(req.params.id);
      if (!fs.existsSync(dir)) return res.status(404).json({ error: `Dossier candidature introuvable : ${req.params.id}` });
      const file = req.params.file;
      if (!CV_FILES.has(file)) return res.status(400).json({ error: 'Fichier CV non autorisé' });
      const filePath = path.join(applicationDir(req.params.id), 'cv', file);
      if (!fs.existsSync(filePath)) return res.status(404).json({ error: `Fichier introuvable : ${file}` });
      res.download(filePath, file);
    } catch (err) {
      console.error('[GET /applications/:id/cv/download/:file]', err.message);
      res.status(400).json({ error: err.message });
    }
  });

  // POST /api/applications/:id/applied — Marque une candidature comme postulée
  router.post('/applications/:id/applied', async (req, res) => {
    try {
      const record = await repo.markApplied(req.params.id);
      res.json(record);
    } catch (err) {
      console.error('[POST /applications/:id/applied]', err.message);
      const status = err.message.includes('introuvable') ? 404 : 500;
      res.status(status).json({ error: err.message });
    }
  });

  // POST /api/applications/:id/not-applied — Annule le statut "postulé"
  router.post('/applications/:id/not-applied', async (req, res) => {
    try {
      const record = await repo.markNotApplied(req.params.id);
      res.json(record);
    } catch (err) {
      console.error('[POST /applications/:id/not-applied]', err.message);
      const status = err.message.includes('introuvable') ? 404 : 500;
      res.status(status).json({ error: err.message });
    }
  });

  return router;
}
