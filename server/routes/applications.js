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
import { spawn } from 'child_process';
import { PROJECT_ROOT } from '../config.js';

const MAX_CV_PROCESS_OUTPUT = 10 * 1024 * 1024;
const CV_PYTHON_BIN = process.env.CV_PYTHON_BIN || 'python3';
const CV_TASK_TIMEOUT_MS = Number.parseInt(
  process.env.CV_TASK_TIMEOUT_MS || String(15 * 60 * 1000),
  10
);
const CV_TASK_KILL_GRACE_MS = 5000;
const CV_TASK_RETENTION_MS = 60 * 60 * 1000;
const REQUIRED_FRESH_CV_FILES = [
  'cv_final.pdf',
  'cv_agent_trace.json',
  'cv_canva_copy.md',
];
const CV_FILES = new Set([
  'cv_adaptation_plan.json',
  'cv_draft.json',
  'cv_draft.md',
  'cv_review.json',
  'cv_final_review.json',
  'cv_final.json',
  'cv_agent_trace.json',
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

function hasFreshCvOutputs(id, startedAtMs) {
  const cvDir = path.join(applicationDir(id), 'cv');
  return REQUIRED_FRESH_CV_FILES.every(file => {
    const filePath = path.join(cvDir, file);
    try {
      return fs.statSync(filePath).mtimeMs >= startedAtMs - 1000;
    } catch {
      return false;
    }
  });
}

function publicCvTask(task) {
  if (!task) return null;
  return {
    state: task.state,
    queued_at: task.queued_at,
    started_at: task.started_at || null,
    completed_at: task.completed_at || null,
    error: task.error || null,
  };
}

export default function createApplicationsRouter(repo) {
  const router = Router();
  const cvTasks = new Map();
  const cvQueue = [];
  let activeCvTask = null;

  function statusWithTask(id) {
    return {
      ...cvStatus(id),
      generation: publicCvTask(cvTasks.get(id)),
    };
  }

  function runCvTask(id, dir, task) {
    task.state = 'running';
    task.started_at = new Date().toISOString();
    const startedAtMs = Date.now();
    const child = spawn(
      CV_PYTHON_BIN,
      ['-m', 'hermes_commands.cv_prepare', '--application-dir', dir],
      {
        cwd: PROJECT_ROOT,
        stdio: ['ignore', 'pipe', 'pipe'],
      }
    );
    let stdout = '';
    let stderr = '';
    let outputBytes = 0;
    let outputExceeded = false;
    let processTimedOut = false;
    let forceKillTimer = null;
    let slotReleased = false;

    const collect = (target, chunk) => {
      outputBytes += chunk.length;
      if (outputBytes > MAX_CV_PROCESS_OUTPUT) {
        outputExceeded = true;
        child.kill('SIGTERM');
        return target;
      }
      return target + chunk.toString('utf-8');
    };

    child.stdout.on('data', chunk => {
      stdout = collect(stdout, chunk);
    });
    child.stderr.on('data', chunk => {
      stderr = collect(stderr, chunk);
    });

    let cleanupScheduled = false;
    const scheduleCleanup = () => {
      if (cleanupScheduled) return;
      cleanupScheduled = true;
      const cleanup = setTimeout(() => {
        if (cvTasks.get(id) === task && task.state !== 'running') {
          cvTasks.delete(id);
        }
      }, CV_TASK_RETENTION_MS);
      cleanup.unref();
    };

    const failTask = message => {
      if (task.state !== 'running') return;
      task.state = 'failed';
      task.error = String(message || 'Erreur inconnue').trim().slice(-4000);
      task.completed_at = new Date().toISOString();
      console.error(`[CV task ${id}] ${task.error}`);
      scheduleCleanup();
    };

    const releaseSlot = () => {
      if (slotReleased) return;
      slotReleased = true;
      if (activeCvTask === task) activeCvTask = null;
      queueMicrotask(pumpCvQueue);
    };

    const taskTimer = setTimeout(() => {
      processTimedOut = true;
      child.kill('SIGTERM');
      forceKillTimer = setTimeout(() => {
        child.kill('SIGKILL');
      }, CV_TASK_KILL_GRACE_MS);
      forceKillTimer.unref();
    }, CV_TASK_TIMEOUT_MS);
    taskTimer.unref();

    child.on('error', err => {
      clearTimeout(taskTimer);
      if (forceKillTimer) clearTimeout(forceKillTimer);
      failTask(`Impossible de démarrer la génération : ${err.message}`);
      releaseSlot();
    });

    child.on('close', code => {
      clearTimeout(taskTimer);
      if (forceKillTimer) clearTimeout(forceKillTimer);
      if (task.state !== 'running') {
        releaseSlot();
        return;
      }
      if (processTimedOut) {
        failTask('La génération du CV a dépassé le délai maximal.');
      } else if (outputExceeded) {
        failTask('La sortie du générateur CV dépasse la limite autorisée.');
      } else if (code !== 0) {
        failTask(`Génération CV impossible : ${stderr || stdout || `code ${code}`}`);
      } else {
        try {
          const payload = JSON.parse(stdout);
          if (payload?.ok !== true) {
            failTask(payload.error || 'Le générateur CV a signalé un échec.');
          } else if (!hasFreshCvOutputs(id, startedAtMs)) {
            failTask("Le générateur n'a pas produit tous les fichiers CV requis.");
          } else {
            task.state = 'completed';
            task.completed_at = new Date().toISOString();
            scheduleCleanup();
          }
        } catch {
          failTask('Le générateur CV a renvoyé une réponse JSON invalide.');
        }
      }
      releaseSlot();
    });
  }

  function pumpCvQueue() {
    if (activeCvTask) return;
    while (cvQueue.length > 0) {
      const queued = cvQueue.shift();
      if (cvTasks.get(queued.id) !== queued.task || queued.task.state !== 'queued') {
        continue;
      }
      activeCvTask = queued.task;
      runCvTask(queued.id, queued.dir, queued.task);
      return;
    }
  }

  function enqueueCvTask(id, dir) {
    const task = {
      state: 'queued',
      queued_at: new Date().toISOString(),
      started_at: null,
      completed_at: null,
      error: null,
    };
    cvTasks.set(id, task);
    cvQueue.push({ id, dir, task });
    pumpCvQueue();
    return task;
  }

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
      res.json(statusWithTask(req.params.id));
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
      const currentTask = cvTasks.get(req.params.id);
      if (!currentTask || !['queued', 'running'].includes(currentTask.state)) {
        enqueueCvTask(req.params.id, dir);
      }
      res.status(202).json({
        accepted: true,
        status: statusWithTask(req.params.id),
      });
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
