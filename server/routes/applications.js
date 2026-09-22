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
import { execFile, spawn } from 'child_process';
import { PROJECT_ROOT } from '../config.js';
import { downloadFilename } from '../services/cvDownloads.js';
import {
  CV_FILES,
  isFinalCvFile,
  resolveCvPublication,
} from '../services/cvPublication.js';
import {
  normalizeDomain,
  validateDomain,
  domainMatchesAgency,
  cleanAgencyName,
  isAlreadyTargeted,
  appendToCSV,
  appendToYAML,
  measureAgency,
  prepareAgency,
  runProspecting,
  sameProspectingRequest,
  readSearchIndex,
  readSearchPayload,
  readPersistedAnalyses
} from '../services/agenciesService.js';

// Vérifie qu'un domaine existe dans la base Agency Scout (SQLite via CLI).
// Le nom affiché vient TOUJOURS de la base, jamais du client.
async function findScoutAgencyByDomain(domain) {
  const pythonBin = process.env.PYTHON_BIN || 'python3';
  const stdout = await new Promise((resolve, reject) => {
    execFile(
      pythonBin,
      ['-m', 'agency_scout', 'list'],
      { cwd: PROJECT_ROOT, timeout: 20000, maxBuffer: 20 * 1024 * 1024 },
      (err, out) => (err ? reject(err) : resolve(out))
    );
  });
  const data = JSON.parse(stdout);
  return (data.agencies || []).find(a => a.domain === domain) || null;
}

const MAX_CV_PROCESS_OUTPUT = 10 * 1024 * 1024;
const CV_PYTHON_BIN = process.env.CV_PYTHON_BIN || 'python3';
const CV_TASK_TIMEOUT_MS = Number.parseInt(
  process.env.CV_TASK_TIMEOUT_MS || String(15 * 60 * 1000),
  10
);
const CV_TASK_KILL_GRACE_MS = 5000;
const CV_TASK_RETENTION_MS = 60 * 60 * 1000;
const PREPARE_TASK_RETENTION_MS = 60 * 60 * 1000;
const AGENCY_TASK_RETENTION_MS = 60 * 60 * 1000;
// Mêmes valeurs que APPROVED_STATUS dans applications/send.py : le front écrit
// exactement ce que la brique envoi contrôle.
const APPROVED_STATUS = 'APPROVED';
const READY_STATUS = 'ready_to_apply';
// Un CV refusé ne produit plus de fichier final : la fraîcheur se mesure donc
// sur les artefacts que le pipeline écrit quel que soit son verdict.
const REQUIRED_FRESH_CV_FILES = [
  'cv_agent_trace.json',
  'cv_assessment.json',
];

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
  let assessment = null;
  const assessmentPath = path.join(cvDir, 'cv_assessment.json');
  if (fs.existsSync(assessmentPath)) {
    try {
      assessment = JSON.parse(fs.readFileSync(assessmentPath, 'utf-8'));
    } catch {
      assessment = null;
    }
  }
  // Étape courante publiée par le pipeline : sans elle l'interface ne peut
  // afficher qu'un « en cours » indifférencié.
  let progress = null;
  const progressPath = path.join(cvDir, 'cv_progress.json');
  if (fs.existsSync(progressPath)) {
    try {
      progress = JSON.parse(fs.readFileSync(progressPath, 'utf-8'));
    } catch {
      progress = null;
    }
  }
  const publication = resolveCvPublication(files, assessment, review);
  return { exists: fs.existsSync(cvDir), files, review, assessment, progress, ...publication };
}

function readApplicationMetadata(id) {
  const metadataPath = path.join(applicationDir(id), 'metadata.json');
  try {
    const metadata = JSON.parse(fs.readFileSync(metadataPath, 'utf-8'));
    return metadata && typeof metadata === 'object' ? metadata : {};
  } catch {
    return {};
  }
}

/**
 * Écrit le statut d'approbation dans metadata.json du dossier.
 *
 * C'est le fichier que lit `applications/send.py` : il n'existe donc qu'une
 * seule réponse à « a-t-on le droit d'envoyer ». Ne pas dupliquer cette
 * information dans le tracker, qui journalise ce qui est arrivé et non ce qui
 * est permis.
 *
 * Écriture atomique : un metadata.json tronqué par une coupure rendrait le
 * dossier illisible pour le front comme pour la brique envoi.
 */
function writeApprovalStatus(id, approved) {
  const dir = applicationDir(id);
  const metadataPath = path.join(dir, 'metadata.json');
  const metadata = readApplicationMetadata(id);
  metadata.status = approved ? APPROVED_STATUS : READY_STATUS;
  metadata.approval_updated_at = new Date().toISOString();
  const temporaryPath = `${metadataPath}.${process.pid}.tmp`;
  fs.writeFileSync(temporaryPath, `${JSON.stringify(metadata, null, 2)}\n`, 'utf-8');
  fs.renameSync(temporaryPath, metadataPath);
  return metadata;
}

function approvalState(id) {
  const metadata = readApplicationMetadata(id);
  return {
    id,
    status: metadata.status || '',
    approved: metadata.status === APPROVED_STATUS,
    approval_updated_at: metadata.approval_updated_at || null,
  };
}

function cvCatalogEntry(id, application = {}) {
  const metadata = readApplicationMetadata(id);
  const status = cvStatus(id);
  const files = status.files;
  const hasAnyFile = Object.values(files).some(Boolean);
  if (!hasAnyFile) return null;

  // `cv_content.json` est écrit quel que soit le verdict : sans lui, un CV en
  // révision n'aurait aucune date et tomberait en fin de catalogue.
  const generatedAt = [
    'cv_content.json',
    'cv_final.pdf',
    'cv_ats.pdf',
    'cv_final.html',
    'cv_final.json',
  ].map(file => {
    try {
      return fs.statSync(path.join(applicationDir(id), 'cv', file)).mtimeMs;
    } catch {
      return 0;
    }
  }).reduce((latest, value) => Math.max(latest, value), 0);

  return {
    id,
    entreprise: application.entreprise || metadata.company || '',
    poste: application.poste || metadata.job_title || '',
    date: application.date || String(metadata.created_at || id).slice(0, 10),
    status: status.status,
    reason: status.reason,
    files,
    generated_at: generatedAt ? new Date(generatedAt).toISOString() : null,
  };
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

  // Un dossier sans CV garde le flux d'avant : le CV est optionnel. Un dossier
  // avec un CV refusé bloque, en disant pourquoi.
  function cvBlocksSending(id) {
    let publication;
    try {
      publication = cvStatus(id);
    } catch {
      return null;
    }
    if (publication.status === 'absent' || publication.status === 'ready') return null;
    return {
      error: "Le CV de cette candidature n'est pas validé.",
      cv_status: publication.status,
      reason: publication.reason,
    };
  }

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

  // ── File de préparation des candidatures ──────────────────────────
  // Le script Python tourne 20-40 s. Garder la requête HTTP ouverte pendant ce
  // temps cassait sur mobile (4G, mise en veille, QUIC) : le dossier était bien
  // créé mais la réponse n'arrivait jamais et le front abandonnait. On répond
  // donc 202 immédiatement et le client suit l'avancement par polling.
  const prepareTasks = new Map();
  let prepareSequence = 0;
  let prepareChain = Promise.resolve();
  const agencyTasks = new Map();
  const activeAgencyTasksByDomain = new Map();
  let agencySequence = 0;
  let agencyChain = Promise.resolve();

  function publicPrepareTask(task) {
    if (!task) return null;
    return {
      task_id: task.task_id,
      state: task.state,
      queued_at: task.queued_at,
      started_at: task.started_at,
      completed_at: task.completed_at,
      error: task.error,
      result: task.result,
    };
  }

  function enqueuePrepareTask(job) {
    prepareSequence += 1;
    const task = {
      task_id: `prep_${Date.now().toString(36)}_${prepareSequence}`,
      state: 'queued',
      queued_at: new Date().toISOString(),
      started_at: null,
      completed_at: null,
      error: null,
      result: null,
    };
    prepareTasks.set(task.task_id, task);

    // Chaîne séquentielle : un seul script Python de préparation à la fois.
    prepareChain = prepareChain.then(async () => {
      task.state = 'running';
      task.started_at = new Date().toISOString();
      try {
        task.result = await repo.prepareFromJob(job);
        task.state = 'completed';
      } catch (err) {
        task.state = 'failed';
        task.error = String(err?.message || err || 'Erreur inconnue').trim().slice(-4000);
        console.error(`[prepare task ${task.task_id}]`, task.error);
      } finally {
        task.completed_at = new Date().toISOString();
        const cleanup = setTimeout(() => {
          prepareTasks.delete(task.task_id);
        }, PREPARE_TASK_RETENTION_MS);
        cleanup.unref();
      }
    });

    return task;
  }

  function publicAgencyTask(task) {
    if (!task) return null;
    return {
      task_id: task.task_id,
      domain: task.domain,
      agency_name: task.agency_name,
      state: task.state,
      stage: task.stage,
      queued_at: task.queued_at,
      started_at: task.started_at,
      completed_at: task.completed_at,
      error: task.error,
      result: task.result,
    };
  }

  function enqueueAgencyTask({ domain, agencyName, alreadyTargeted }) {
    const activeTask = activeAgencyTasksByDomain.get(domain);
    if (activeTask && ['queued', 'running'].includes(activeTask.state)) {
      return activeTask;
    }

    agencySequence += 1;
    const task = {
      task_id: `agency_${Date.now().toString(36)}_${agencySequence}`,
      domain,
      agency_name: agencyName,
      state: 'queued',
      stage: 'queued',
      queued_at: new Date().toISOString(),
      started_at: null,
      completed_at: null,
      error: null,
      result: null,
    };
    agencyTasks.set(task.task_id, task);
    activeAgencyTasksByDomain.set(domain, task);

    agencyChain = agencyChain.then(async () => {
      task.state = 'running';
      task.stage = 'mesure';
      task.started_at = new Date().toISOString();

      try {
        const measureResult = await measureAgency(agencyName);
        if (!measureResult.ok) {
          task.state = 'failed';
          task.error = measureResult.error || measureResult.reason || 'Mesure impossible';
          task.result = measureResult;
          console.error(`[agency task ${task.task_id}]`, task.error);
          return;
        }

        task.stage = 'préparation';
        const prepareResult = await prepareAgency(measureResult.number, agencyName);
        if (!prepareResult.ok) {
          task.state = 'failed';
          task.error = prepareResult.error || 'Préparation impossible';
          task.result = prepareResult;
          console.error(`[agency task ${task.task_id}]`, task.error);
          return;
        }

        task.state = 'completed';
        task.stage = 'completed';
        task.result = {
          ok: true,
          domain,
          number: measureResult.number,
          constats_confirmes: measureResult.constats,
          already_targeted: alreadyTargeted,
          dry: false,
        };
      } catch (err) {
        task.state = 'failed';
        task.error = String(err?.message || err || 'Erreur inconnue').trim().slice(-4000);
        console.error(`[agency task ${task.task_id}]`, task.error);
      } finally {
        task.completed_at = new Date().toISOString();
        if (activeAgencyTasksByDomain.get(domain) === task) {
          activeAgencyTasksByDomain.delete(domain);
        }
        const cleanup = setTimeout(() => {
          agencyTasks.delete(task.task_id);
        }, AGENCY_TASK_RETENTION_MS);
        cleanup.unref();
      }
    });

    return task;
  }

  // ── File de prospection d'agences ─────────────────────────────────
  // Distincte de la file `agencyTasks` : celle-ci *découvre* des agences (crawl +
  // géocodage, plusieurs minutes), l'autre *cible* une agence déjà connue.
  const searchTasks = new Map();
  let searchSequence = 0;
  let searchChain = Promise.resolve();
  let activeSearchTask = null;

  function publicSearchTask(task) {
    if (!task) return null;
    return {
      task_id: task.task_id,
      zone: task.zone,
      // Ville demandée et ville résolue restent distinctes : « Montreuil »
      // demandé, « Montreuil (93) » résolu. Les confondre masquerait une
      // résolution qui aurait choisi un autre département que celui voulu.
      city: task.city,
      departement: task.departement,
      resolved_city: task.result?.city || null,
      radius_m: task.radius_m,
      // Identifiant de la recherche produite : le front sait quoi sélectionner
      // au retour, sans deviner « la plus récente ».
      search_id: task.result?.search_id || null,
      // Étapes mesurées par le script : de quoi distinguer un run lent d'un run
      // bloqué pendant les minutes où il n'y a rien d'autre à afficher.
      steps: task.result?.steps || [],
      state: task.state,
      queued_at: task.queued_at,
      started_at: task.started_at,
      completed_at: task.completed_at,
      error: task.error,
      result: task.result,
    };
  }

  function enqueueSearchTask({ zone = null, city = null, departement = null, radiusM }) {
    // Une seule prospection à la fois : deux crawls concurrents se disputeraient
    // le quota de géocodage Nominatim et écriraient tous deux latest.json.
    // Deux villes différentes restent deux tâches : elles s'exécutent l'une
    // après l'autre, sans jamais partager un task_id ni un résultat.
    const duplicate = [...searchTasks.values()].find(task =>
      ['queued', 'running'].includes(task.state)
      && sameProspectingRequest(task, { zone, city, departement, radiusM })
    );
    if (duplicate) {
      return duplicate;
    }

    searchSequence += 1;
    const task = {
      task_id: `agency_search_${Date.now().toString(36)}_${searchSequence}`,
      zone,
      city,
      departement,
      radius_m: radiusM,
      state: 'queued',
      queued_at: new Date().toISOString(),
      started_at: null,
      completed_at: null,
      error: null,
      result: null,
    };
    searchTasks.set(task.task_id, task);
    activeSearchTask = task;

    searchChain = searchChain.then(async () => {
      task.state = 'running';
      task.started_at = new Date().toISOString();
      try {
        task.result = await runProspecting({ zone, city, departement, radiusM });
        task.state = 'completed';
      } catch (err) {
        task.state = 'failed';
        task.error = String(err?.message || err || 'Erreur inconnue').trim().slice(-4000);
        console.error(`[agency search ${task.task_id}]`, task.error);
      } finally {
        task.completed_at = new Date().toISOString();
        if (activeSearchTask === task) activeSearchTask = null;
        const cleanup = setTimeout(() => {
          searchTasks.delete(task.task_id);
        }, AGENCY_TASK_RETENTION_MS);
        cleanup.unref();
      }
    });

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

  // GET /api/applications/cvs — Catalogue des CV réellement générés
  router.get('/applications/cvs', async (_req, res) => {
    try {
      const applications = await repo.getAll();
      const byId = new Map(applications.map(application => [application.id, application]));
      const base = path.resolve(PROJECT_ROOT, 'output/applications');
      if (!fs.existsSync(base)) return res.json([]);
      const entries = fs.readdirSync(base, { withFileTypes: true })
        .filter(entry => entry.isDirectory())
        .map(entry => cvCatalogEntry(entry.name, byId.get(entry.name)))
        .filter(Boolean)
        .sort((a, b) => (b.generated_at || '').localeCompare(a.generated_at || ''));
      res.json(entries);
    } catch (err) {
      console.error('[GET /applications/cvs]', err.message);
      res.status(500).json({ error: 'Erreur lors de la récupération des CV générés' });
    }
  });

  // POST /api/applications/prepare — Met la génération de candidature en file
  router.post('/applications/prepare', (req, res) => {
    const job = req.body?.job;
    if (!job || typeof job !== 'object') {
      return res.status(400).json({ error: 'Offre invalide' });
    }
    if (!job.title && !job.url) {
      return res.status(400).json({ error: 'Offre invalide : titre ou URL requis' });
    }
    const task = enqueuePrepareTask(job);
    res.status(202).json({
      accepted: true,
      task_id: task.task_id,
      status: publicPrepareTask(task),
    });
  });

  // GET /api/applications/prepare/status/:taskId — Suivi de la préparation
  router.get('/applications/prepare/status/:taskId', (req, res) => {
    const task = prepareTasks.get(req.params.taskId);
    if (!task) {
      return res.status(404).json({ error: 'Tâche de préparation introuvable ou expirée' });
    }
    res.json(publicPrepareTask(task));
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

  // POST /api/applications/:id/send — Envoi réel du dossier via applications.send
  // (Brevo si BREVO_API_KEY, sinon relais SMTP). Le clic front est le verrou
  // humain ; la chaîne Python refuse tout dossier sans constat vérifié.
  // ?dry=1 : mêmes contrôles, aucun fournisseur construit, rien ne part.
  router.post('/applications/:id/send', async (req, res) => {
    const dry = req.query.dry === '1';
    try {
      const dir = applicationDir(req.params.id);
      if (!fs.existsSync(dir)) return res.status(404).json({ error: `Dossier candidature introuvable : ${req.params.id}` });
      const args = ['-m', 'applications.send', '--dossier', dir, '--json'];
      if (!dry) args.push('--send');
      const stdout = await new Promise((resolve, reject) => {
        execFile(
          CV_PYTHON_BIN,
          args,
          { cwd: PROJECT_ROOT, timeout: 120000, maxBuffer: 20 * 1024 * 1024 },
          (err, out) => (out ? resolve(out) : reject(err || new Error('sortie vide')))
        );
      });
      let result;
      try {
        result = JSON.parse(stdout.slice(stdout.indexOf('{')));
      } catch {
        // send.py sort « ENVOI IMPOSSIBLE » quand aucun fournisseur n'est configuré.
        if (stdout.includes('ENVOI IMPOSSIBLE')) {
          return res.status(503).json({ error: 'Fournisseur d\u2019envoi non configuré : définir BREVO_API_KEY (ou SMTP sortant).' });
        }
        return res.status(500).json({ error: stdout.slice(-300) || 'Erreur inconnue du sendeur' });
      }
      if (result.refused) {
        return res.status(409).json({ ok: false, refused: true, refusal: result.refusal, verdicts: result.verdicts });
      }
      if (result.send_error) {
        return res.status(502).json({ ok: false, error: result.send_error });
      }
      res.json({
        ok: true,
        sent: result.sent === true,
        dry: dry,
        would_send: result.would_send,
        attachments: result.attachments || [],
        message_id: result.message_id || null,
      });
    } catch (err) {
      console.error('[POST /applications/:id/send]', err.message);
      res.status(500).json({ error: err.message });
    }
  });

  // POST /api/applications/:id/contact — Ajout manuel d'une adresse email
  // pour une agence trouvée sans mail. Le constat cite sa source honnête :
  // « ajout manuel par Cundo ». Il devient l'adresse de destination.
  router.post('/applications/:id/contact', async (req, res) => {
    try {
      const email = String(req.body?.email || '').trim().toLowerCase();
      if (!/^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(email)) {
        return res.status(400).json({ error: 'Adresse email invalide.' });
      }
      const jobPath = path.join(applicationDir(req.params.id), 'job.json');
      if (!fs.existsSync(jobPath)) return res.status(404).json({ error: 'Pas de job.json de prospection pour ce dossier.' });
      const job = JSON.parse(fs.readFileSync(jobPath, 'utf-8'));
      const contacts = Array.isArray(job.public_contact) ? job.public_contact : [];
      if (JSON.stringify(contacts).toLowerCase().includes(email)) {
        return res.json({ ok: true, adresse: email, deja_presente: true });
      }
      contacts.push({
        claim: `Adresse email ajoutée à la main : ${email}`,
        evidence: [`ajout manuel par Cundo le ${new Date().toISOString().slice(0, 10)}`],
        status: 'CONFIRMED',
        source_tool: 'ajout_manuel',
        category: 'contact',
      });
      job.public_contact = contacts;
      fs.writeFileSync(jobPath, JSON.stringify(job, null, 2), 'utf-8');
      // L'adresse lue par le front vient de l'index : on le reconstruit.
      await new Promise((resolve, reject) => {
        execFile(
          CV_PYTHON_BIN,
          ['-c', "from applications.candidatures_index import rebuild_candidatures_index as r; print(r('output/applications', 'front/public/data/candidatures.json'))"],
          { cwd: PROJECT_ROOT, timeout: 60000 },
          (err, out) => (err ? reject(err) : resolve(out))
        );
      });
      res.json({ ok: true, adresse: email });
    } catch (err) {
      console.error('[POST /applications/:id/contact]', err.message);
      res.status(500).json({ error: err.message });
    }
  });

  // POST /api/applications/:id/lettre/regenerate — Régénère le PDF de la
  // lettre depuis le markdown (après édition manuelle de lettre_motivation.md).
  router.post('/applications/:id/lettre/regenerate', async (req, res) => {
    try {
      const dir = applicationDir(req.params.id);
      const mdPath = path.join(dir, 'lettre_motivation.md');
      if (!fs.existsSync(mdPath)) return res.status(404).json({ error: 'Aucune lettre à régénérer pour ce dossier.' });
      await new Promise((resolve, reject) => {
        execFile(
          CV_PYTHON_BIN,
          ['-c', "import sys; from cv_generator.exporters import lettre_to_pdf; lettre_to_pdf(sys.argv[1], sys.argv[2])", mdPath, path.join(dir, 'lettre_motivation.pdf')],
          { cwd: PROJECT_ROOT, timeout: 60000 },
          (err, out) => (err ? reject(err) : resolve(out))
        );
      });
      res.json({ ok: true, regenerated_at: new Date().toISOString() });
    } catch (err) {
      console.error('[POST /applications/:id/lettre/regenerate]', err.message);
      res.status(500).json({ error: err.message });
    }
  });

  // GET /api/applications/:id/lettre/download — Lettre de motivation en PDF
  router.get('/applications/:id/lettre/download', async (req, res) => {
    try {
      const dir = applicationDir(req.params.id);
      if (!fs.existsSync(dir)) return res.status(404).json({ error: `Dossier candidature introuvable : ${req.params.id}` });
      const filePath = path.join(dir, 'lettre_motivation.pdf');
      if (!fs.existsSync(filePath)) return res.status(404).json({ error: 'Aucun PDF de lettre pour ce dossier' });
      const application = await repo.getById(req.params.id);
      const metadata = readApplicationMetadata(req.params.id);
      res.download(filePath, downloadFilename(application || {
        entreprise: metadata.company,
        poste: metadata.job_title,
      }, 'Lettre.pdf'));
    } catch (err) {
      console.error('[GET /applications/:id/lettre/download]', err.message);
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
      // Un fichier final n'est servi que si le CV est réellement validé : sinon
      // on distribuerait un CV que le pipeline a refusé.
      if (isFinalCvFile(file)) {
        const publication = cvStatus(req.params.id);
        if (publication.status !== 'ready') {
          return res.status(409).json({
            error: "Ce CV n'est pas validé : le téléchargement final est refusé.",
            cv_status: publication.status,
            reason: publication.reason,
          });
        }
      }
      const filePath = path.join(applicationDir(req.params.id), 'cv', file);
      if (!fs.existsSync(filePath)) return res.status(404).json({ error: `Fichier introuvable : ${file}` });
      const application = await repo.getById(req.params.id);
      const metadata = readApplicationMetadata(req.params.id);
      res.download(filePath, downloadFilename(application || {
        entreprise: metadata.company,
        poste: metadata.job_title,
      }, file));
    } catch (err) {
      console.error('[GET /applications/:id/cv/download/:file]', err.message);
      res.status(400).json({ error: err.message });
    }
  });

  // GET /api/applications/:id/approval — Le dossier est-il autorisé à partir ?
  router.get('/applications/:id/approval', (req, res) => {
    try {
      const dir = applicationDir(req.params.id);
      if (!fs.existsSync(dir)) return res.status(404).json({ error: `Dossier candidature introuvable : ${req.params.id}` });
      res.json(approvalState(req.params.id));
    } catch (err) {
      console.error('[GET /applications/:id/approval]', err.message);
      res.status(400).json({ error: err.message });
    }
  });

  // POST /api/applications/:id/approval — Pose ou retire l'autorisation d'envoi.
  // N'envoie rien : seul l'utilisateur lance `python -m applications.send`.
  router.post('/applications/:id/approval', (req, res) => {
    try {
      const approved = req.body?.approved;
      if (typeof approved !== 'boolean') {
        return res.status(400).json({ error: 'Champ "approved" booléen requis' });
      }
      const dir = applicationDir(req.params.id);
      if (!fs.existsSync(dir)) return res.status(404).json({ error: `Dossier candidature introuvable : ${req.params.id}` });
      // Le CV reste optionnel : sans CV généré, rien ne change. Mais un CV
      // généré et refusé ne doit pas partir avec la candidature.
      const blocked = approved ? cvBlocksSending(req.params.id) : null;
      if (blocked) return res.status(409).json(blocked);
      writeApprovalStatus(req.params.id, approved);
      res.json(approvalState(req.params.id));
    } catch (err) {
      console.error('[POST /applications/:id/approval]', err.message);
      res.status(400).json({ error: err.message });
    }
  });

  // POST /api/applications/:id/applied — Marque une candidature comme postulée
  router.post('/applications/:id/applied', async (req, res) => {
    try {
      const blocked = cvBlocksSending(req.params.id);
      if (blocked) return res.status(409).json(blocked);
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

  // POST /api/agencies/search — Lance une passe de prospection (découverte)
  // Répond 202 : le crawl et les géocodages durent plusieurs minutes.
  router.post('/agencies/search', (req, res) => {
    const city = String(req.body?.city || '').trim();
    const departement = String(req.body?.departement || '').trim();
    const rawZone = String(req.body?.zone || '').trim();
    const radiusM = req.body?.radius_m ?? null;

    if (city && rawZone) {
      return res.status(400).json({
        error: 'city et zone sont exclusifs : zone rejoue un préréglage historique, '
          + 'city résout une commune réelle. Envoie l’un des deux.',
      });
    }
    // Sans ville ni zone, on reste sur le préréglage historique : les clients
    // déjà déployés continuent de fonctionner sans changement.
    const zone = city ? null : (rawZone || 'ile-de-france');

    if (radiusM != null && (!Number.isInteger(Number(radiusM)) || Number(radiusM) <= 0)) {
      return res.status(400).json({ error: 'radius_m doit être un nombre de mètres positif' });
    }

    try {
      const task = enqueueSearchTask({
        zone,
        city: city || null,
        departement: departement || null,
        radiusM: radiusM == null ? null : Number(radiusM),
      });
      res.status(202).json({
        accepted: true,
        task_id: task.task_id,
        status: publicSearchTask(task),
      });
    } catch (err) {
      res.status(400).json({ error: err.message });
    }
  });

  // GET /api/agencies/search/status/:taskId — Suit la passe de prospection
  router.get('/agencies/search/status/:taskId', (req, res) => {
    const task = searchTasks.get(req.params.taskId);
    if (!task) {
      return res.status(404).json({ error: 'Tâche de prospection introuvable ou expirée' });
    }
    res.json(publicSearchTask(task));
  });

  // GET /api/agencies/searches — Index des recherches publiées (le plus récent d'abord)
  // Route JSON plutôt que fichier statique : le front doit pouvoir distinguer
  // « pas encore d'index » de « index vide », ce qu'un 404 statique ne dit pas.
  router.get('/agencies/searches', (_req, res) => {
    try {
      res.json(readSearchIndex());
    } catch (err) {
      console.error('[GET /agencies/searches]', err.message);
      res.status(500).json({ error: err.message });
    }
  });

  // GET /api/agencies/searches/:searchId — Résultats d'UNE recherche
  // `latest` reste accepté comme alias de compatibilité.
  router.get('/agencies/searches/:searchId', (req, res) => {
    try {
      const { payload, search_id, source } = readSearchPayload(req.params.searchId);
      res.json({ ...payload, search_id, source });
    } catch (err) {
      // Un identifiant inconnu est refusé en nommant les recherches connues,
      // jamais par une liste vide.
      res.status(404).json({ error: err.message });
    }
  });

  // GET /api/agencies/analyses — Analyses persistées, en lecture seule
  router.get('/agencies/analyses', (_req, res) => {
    try {
      res.json(readPersistedAnalyses());
    } catch (err) {
      console.error('[GET /agencies/analyses]', err.message);
      res.status(500).json({ error: err.message });
    }
  });

  // POST /api/agencies/target — Ajoute une agence puis met la préparation en file
  // Deux sources : 'search' (défaut) relit l'agence dans la passe affichée
  // (search_id) ; 'scout' vérifie le domaine dans la base Agency Scout
  // (SQLite via CLI) — jamais le nom venu du client. La suite est commune :
  // idempotence CSV, banc d'essai, file de tâche, task_id pollable.
  router.post('/agencies/target', async (req, res) => {
    const domain = req.body?.domain;
    const dry = req.body?.dry === true;
    const source = req.body?.source === 'scout' ? 'scout' : 'search';
    // Le ciblage doit porter sur la recherche AFFICHÉE : sans search_id, deux
    // passes de villes différentes donneraient la même agence « la plus récente ».
    const searchId = req.body?.search_id ?? null;

    // Validation
    if (!domain || typeof domain !== 'string') {
      return res.status(400).json({ error: 'Domaine manquant ou invalide' });
    }

    const normalizedDomain = normalizeDomain(domain);
    if (!validateDomain(normalizedDomain)) {
      return res.status(400).json({ error: 'Format de domaine invalide' });
    }

    if (source === 'scout' && searchId) {
      return res.status(400).json({ error: 'search_id est incompatible avec source=scout' });
    }

    let displayNameSource = null;
    let scoutRow = null;
    let resolved = null;

    try {
      if (source === 'scout') {
        try {
          scoutRow = await findScoutAgencyByDomain(normalizedDomain);
        } catch (err) {
          console.error('[POST /agencies/target] Agency Scout indisponible:', err.message);
          return res.status(500).json({ error: `Agency Scout indisponible : ${err.message}` });
        }
        if (!scoutRow) {
          return res.status(404).json({
            error: `Domaine ${normalizedDomain} absent de la base Agency Scout — relance un scan ou vérifie le domaine`
          });
        }
        displayNameSource = scoutRow.name;
      } else {
        try {
          // Charger la recherche demandée (repli contrôlé sur latest.json)
          resolved = readSearchPayload(searchId);
        } catch (err) {
          return res.status(404).json({ error: err.message });
        }

        const agencies = resolved.payload.agencies || [];

        // Trouver l'agence
        const agency = agencies.find(a => domainMatchesAgency(normalizedDomain, a));
        if (!agency) {
          return res.status(404).json({
            error: `Agence avec domaine ${normalizedDomain} non trouvée dans la recherche « ${resolved.search_id} »`
          });
        }
        displayNameSource = agency.name;
      }

      // Vérifier idempotence
      const csvPath = path.join(PROJECT_ROOT, 'config/companies.csv');
      const yamlPath = path.join(PROJECT_ROOT, 'config/companies.yaml');
      // Nom nettoyé : évite qu'un « Voir » scrapé pollue csv → mesure → lettre
      const displayName = cleanAgencyName(displayNameSource, normalizedDomain);
      const alreadyTargeted = isAlreadyTargeted(normalizedDomain, csvPath);

      if (!dry && !alreadyTargeted) {
        // Ajouter append-only. Le scout apporte une adresse Google vérifiée :
        // statut « retenue » + adresse/CP écrits dans le banc d'essai.
        const scoutOptions = scoutRow ? {
          statut: 'retenue',
          adresse: scoutRow.address || '',
          codePostal: (String(scoutRow.address || '').match(/\b(\d{5})\b/) || [])[1] || '',
        } : undefined;
        appendToCSV(csvPath, displayName, normalizedDomain, scoutOptions);
        appendToYAML(yamlPath, displayName, normalizedDomain, scoutOptions);
        console.log(`[POST /agencies/target] Agence ${displayName} ajoutée au ciblage (source: ${source})`);
      }

      if (dry) {
        return res.json({
          ok: true,
          domain: normalizedDomain,
          dry: true,
          already_targeted: alreadyTargeted,
          agency_name: displayName,
          source,
          search_id: resolved ? resolved.search_id : null
        });
      }

      const task = enqueueAgencyTask({
        domain: normalizedDomain,
        agencyName: displayName,
        alreadyTargeted,
      });
      res.status(202).json({
        accepted: true,
        task_id: task.task_id,
        source,
        search_id: resolved ? resolved.search_id : null,
        status: publicAgencyTask(task),
      });
    } catch (err) {
      console.error('[POST /agencies/target]', err.message);
      res.status(500).json({ error: err.message });
    }
  });

  // GET /api/agencies/target/status/:taskId — Suit mesure, candidature et CV
  router.get('/agencies/target/status/:taskId', (req, res) => {
    const task = agencyTasks.get(req.params.taskId);
    if (!task) {
      return res.status(404).json({ error: 'Tâche agence introuvable ou expirée' });
    }
    res.json(publicAgencyTask(task));
  });

  return router;
}
