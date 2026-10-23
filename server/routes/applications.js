/**
 * routes/applications.js — Endpoints REST pour les candidatures.
 *
 * Les routes ne connaissent QUE l'interface du repository.
 * Elles ne savent pas si la donnée vient de JSON ou d'une BDD.
 * L'envoi vit dans routes/sending.js, la prospection d'agences dans
 * routes/agencies.js, les fonctions de dossier dans services/applicationFiles.js.
 *
 * @param {import('../repositories/applicationsRepository.js').default} repo
 */
import express, { Router } from 'express';
import fs from 'fs';
import path from 'path';
import { spawn } from 'child_process';
import { PROJECT_ROOT } from '../config.js';
import { downloadFilename } from '../services/cvDownloads.js';
import { readJobOffer } from '../services/jobOffer.js';
import { runPython } from '../services/python.js';
import {
  CV_FILES,
  isFinalCvFile,
  UPLOADED_CV_PDF,
  USER_VALIDATION_FILE,
  USER_VALIDATED_PDF,
  EDITED_CV_JSON,
  EDITED_CV_PDF,
} from '../services/cvPublication.js';
import {
  MAX_CV_PROCESS_OUTPUT,
  CV_PYTHON_BIN,
  CV_TASK_TIMEOUT_MS,
  CV_TASK_KILL_GRACE_MS,
  CV_TASK_RETENTION_MS,
  PREPARE_TASK_RETENTION_MS,
  rebuildCandidaturesIndex,
  applicationDir,
  cvStatus,
  fileSha256,
  readApplicationMetadata,
  hasSendRecord,
  writeApprovalStatus,
  customAttachmentNames,
  cvCatalogEntry,
  hasFreshCvOutputs,
  publicCvTask,
  cvBlocksSending,
} from '../services/applicationFiles.js';

// Le PDF de la lettre suit les règles du dossier (bandeau sans Portfolio pour
// la médiation) : il passe par applications.letter_pdf, jamais par
// lettre_to_pdf appelé à nu.
function writeLetterPdf(dir) {
  return runPython(['-m', 'applications.letter_pdf', dir], { timeout: 60000 });
}



export default function createApplicationsRouter(repo) {
  const router = Router();
  const cvTasks = new Map();
  const cvQueue = [];
  let activeCvTask = null;


  function archiveEditedCv(dir) {
    const cvDir = path.join(dir, 'cv');
    const editPath = path.join(cvDir, EDITED_CV_JSON);
    if (!fs.existsSync(editPath)) return;
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    fs.renameSync(editPath, path.join(cvDir, `cv_edit.archive-${stamp}.json`));
    for (const file of [EDITED_CV_PDF, 'cv_edit_ats.pdf']) {
      fs.rmSync(path.join(cvDir, file), { force: true });
    }
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

  // `run` produit le résultat : préparation d'une offre ou régénération
  // d'une lettre existante. Les deux partagent la même file (un seul script
  // Python à la fois) et le même suivi /applications/prepare/status.
  function enqueuePrepareTask(run) {
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
        task.result = await run();
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
    // Consignes du candidat : optionnelles, bornées ici comme en Python.
    // Elles partent dans job.json, jamais dans la description de l'offre.
    const consignes = String(job.candidate_instructions || '').trim().slice(0, 2000);
    const mailNote = String(job.mail_personal_note || '').trim().slice(0, 1000);
    const cleanJob = { ...job };
    delete cleanJob.candidate_instructions;
    delete cleanJob.mail_personal_note;
    if (consignes) cleanJob.candidate_instructions = consignes;
    if (mailNote) cleanJob.mail_personal_note = mailNote;
    const task = enqueuePrepareTask(() => repo.prepareFromJob(cleanJob));
    res.status(202).json({
      accepted: true,
      task_id: task.task_id,
      status: publicPrepareTask(task),
    });
  });

  // POST /api/applications/:id/lettre/prepare — Réécrit lettre + mail avec
  // de nouvelles consignes. Refusé une fois une tentative d'envoi faite : ce
  // qui est parti ne se réécrit pas. L'approbation tombe côté Python.
  const regeneratingLetters = new Set();
  router.post('/applications/:id/lettre/prepare', (req, res) => {
    try {
      const id = req.params.id;
      const dir = applicationDir(id);
      if (!fs.existsSync(dir)) return res.status(404).json({ error: `Dossier candidature introuvable : ${id}` });
      if (hasSendRecord(id)) return res.status(409).json({ error: 'Ce dossier possède déjà une tentative d’envoi ; sa lettre est verrouillée.' });
      if (regeneratingLetters.has(id)) return res.status(409).json({ error: 'Une régénération est déjà en cours pour ce dossier.' });
      const consignes = String(req.body?.consignes ?? '').trim().slice(0, 2000);
      const mailNote = String(req.body?.mail_note ?? '').trim().slice(0, 1000);
      regeneratingLetters.add(id);
      const task = enqueuePrepareTask(async () => {
        try {
          return await repo.regenerateLetter(id, { consignes, mailNote });
        } finally {
          regeneratingLetters.delete(id);
        }
      });
      res.status(202).json({ accepted: true, task_id: task.task_id, status: publicPrepareTask(task) });
    } catch (err) {
      console.error('[POST /applications/:id/lettre/prepare]', err.message);
      res.status(400).json({ error: err.message });
    }
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
      // Recommandations candidat → job.json : la chaîne CV les passe aux
      // agents (création + révision) comme « consignes_candidat ». Champ
      // vide = on les retire (régénération sans consignes).
      if (typeof req.body?.recommandations === 'string') {
        const jobPath = path.join(dir, 'job.json');
        if (fs.existsSync(jobPath)) {
          const job = JSON.parse(fs.readFileSync(jobPath, 'utf-8'));
          const reco = req.body.recommandations.trim().slice(0, 2000);
          if (reco) job.candidate_instructions = reco;
          else delete job.candidate_instructions;
          fs.writeFileSync(jobPath, JSON.stringify(job, null, 2), 'utf-8');
        }
      }
      const currentTask = cvTasks.get(req.params.id);
      if (!currentTask || !['queued', 'running'].includes(currentTask.state)) {
        // Régénérer, c'est demander un nouveau CV : ta version modifiée de
        // l'ancien est mise de côté (renommée, jamais effacée), sans quoi elle
        // continuerait de remplacer le CV qu'on vient de demander.
        archiveEditedCv(dir);
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

  // GET /api/applications/:id/offre — l'annonce telle que les agents l'ont lue
  router.get('/applications/:id/offre', (req, res) => {
    try {
      const dir = applicationDir(req.params.id);
      if (!fs.existsSync(dir)) return res.status(404).json({ error: `Dossier candidature introuvable : ${req.params.id}` });
      res.json(readJobOffer(dir));
    } catch (err) {
      res.status(400).json({ error: err.message });
    }
  });

  // GET /api/applications/:id/recommandations — consignes candidat actuelles
  router.get('/applications/:id/recommandations', async (req, res) => {
    try {
      const jobPath = path.join(applicationDir(req.params.id), 'job.json');
      if (!fs.existsSync(jobPath)) return res.json({ recommandations: '' });
      const job = JSON.parse(fs.readFileSync(jobPath, 'utf-8'));
      res.json({ recommandations: String(job.candidate_instructions || '') });
    } catch (err) {
      res.status(500).json({ error: err.message });
    }
  });

  // PUT /api/applications/:id/doc/:kind — Enregistre le texte édité dans
  // l'interface (lettre ou mail). La lettre regénère son PDF : ce qui part
  // en pièce jointe est toujours la version enregistrée.
  router.put('/applications/:id/doc/:kind', async (req, res) => {
    try {
      const files = { lettre: 'lettre_motivation.md', mail: 'mail_candidature.md' };
      const fileName = files[req.params.kind];
      if (!fileName) return res.status(400).json({ error: 'Type inconnu : lettre ou mail.' });
      const contenu = String(req.body?.contenu ?? '');
      if (!contenu.trim()) return res.status(400).json({ error: 'Contenu vide.' });
      if (contenu.length > 100_000) return res.status(413).json({ error: 'Contenu trop long.' });
      const dir = applicationDir(req.params.id);
      if (!fs.existsSync(dir)) return res.status(404).json({ error: `Dossier candidature introuvable : ${req.params.id}` });
      fs.writeFileSync(path.join(dir, fileName), contenu, 'utf-8');
      let pdf = null;
      if (req.params.kind === 'lettre') {
        await writeLetterPdf(dir);
        pdf = 'lettre_motivation.pdf';
      }
      // Le fichier est écrit : l'enregistrement a réussi quoi qu'il arrive
      // ensuite. Un index qu'on n'a pas su reconstruire se dit, il ne
      // transforme pas une sauvegarde réussie en erreur.
      let indexed = true;
      let indexError = null;
      try {
        await rebuildCandidaturesIndex();
      } catch (err) {
        indexed = false;
        indexError = err.message;
        console.error('[PUT /applications/:id/doc/:kind] index', err.message);
      }
      res.json({
        ok: true,
        file: fileName,
        bytes: Buffer.byteLength(contenu, 'utf-8'),
        pdf,
        indexed,
        index_error: indexError,
      });
    } catch (err) {
      console.error('[PUT /applications/:id/doc/:kind]', err.message);
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
      await writeLetterPdf(dir);
      // Le markdown a pu être édité hors interface : l'index doit suivre.
      let indexed = true;
      try {
        await rebuildCandidaturesIndex();
      } catch (err) {
        indexed = false;
        console.error('[POST /applications/:id/lettre/regenerate] index', err.message);
      }
      res.json({ ok: true, regenerated_at: new Date().toISOString(), indexed });
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
      const custom = customAttachmentNames(metadata).lettre;
      res.download(filePath, custom || downloadFilename(application || {
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
      // Un aperçu que tu as validé se télécharge sous le nom d'un CV, pas « À corriger ».
      const sentAsCv = file === 'cv_final.pdf' || file === UPLOADED_CV_PDF || file === EDITED_CV_PDF
        || (file === USER_VALIDATED_PDF && cvStatus(req.params.id).status === 'validated');
      const downloadAs = sentAsCv ? 'cv_final.pdf' : file;
      const custom = sentAsCv ? customAttachmentNames(metadata).cv : '';
      res.download(filePath, custom || downloadFilename(application || {
        entreprise: metadata.company,
        poste: metadata.job_title,
      }, downloadAs));
    } catch (err) {
      console.error('[GET /applications/:id/cv/download/:file]', err.message);
      res.status(400).json({ error: err.message });
    }
  });

  // PUT /api/applications/:id/cv/upload — corps = le PDF (application/pdf).
  // Ton CV remplace le CV généré (ou en tient lieu s'il n'y en a pas) : c'est
  // lui qui part à l'envoi. Ce qui partirait change : l'approbation tombe.
  router.put(
    '/applications/:id/cv/upload',
    express.raw({ type: ['application/pdf', 'application/octet-stream'], limit: '10mb' }),
    (req, res) => {
      try {
        const id = req.params.id;
        const dir = applicationDir(id);
        if (!fs.existsSync(dir)) return res.status(404).json({ error: `Dossier candidature introuvable : ${id}` });
        if (hasSendRecord(id)) return res.status(409).json({ error: 'Ce dossier possède déjà une tentative d’envoi ; son CV est verrouillé.' });
        const body = Buffer.isBuffer(req.body) ? req.body : null;
        if (!body || body.length < 5 || body.subarray(0, 5).toString('latin1') !== '%PDF-') {
          return res.status(400).json({ error: 'Le fichier doit être un PDF.' });
        }
        const cvDir = path.join(dir, 'cv');
        fs.mkdirSync(cvDir, { recursive: true });
        fs.writeFileSync(path.join(cvDir, UPLOADED_CV_PDF), body);
        writeApprovalStatus(id, false);
        res.json({ ...statusWithTask(id), approved: false });
      } catch (err) {
        console.error('[PUT /applications/:id/cv/upload]', err.message);
        res.status(400).json({ error: err.message });
      }
    },
  );

  // DELETE /api/applications/:id/cv/upload — retire ton CV : le CV généré
  // (s'il existe et qu'il est validé) redevient celui qui part.
  router.delete('/applications/:id/cv/upload', (req, res) => {
    try {
      const id = req.params.id;
      const dir = applicationDir(id);
      if (!fs.existsSync(dir)) return res.status(404).json({ error: `Dossier candidature introuvable : ${id}` });
      if (hasSendRecord(id)) return res.status(409).json({ error: 'Ce dossier possède déjà une tentative d’envoi ; son CV est verrouillé.' });
      const filePath = path.join(dir, 'cv', UPLOADED_CV_PDF);
      if (fs.existsSync(filePath)) fs.unlinkSync(filePath);
      writeApprovalStatus(id, false);
      res.json({ ...statusWithTask(id), approved: false });
    } catch (err) {
      console.error('[DELETE /applications/:id/cv/upload]', err.message);
      res.status(400).json({ error: err.message });
    }
  });

  // ── Éditeur : ta version du CV (demande Cundo 22/10/2026) ──────────────
  // GET  /api/applications/:id/cv/edit — la version à éditer : la tienne si
  //      elle existe, sinon le CV généré (quel que soit son verdict).
  // PUT  /api/applications/:id/cv/edit — { cv } : enregistre ta version, refait
  //      les PDF sans IA. Elle remplace le CV généré à l'envoi.
  // DELETE /api/applications/:id/cv/edit — retire ta version.
  router.get('/applications/:id/cv/edit', async (req, res) => {
    try {
      const dir = applicationDir(req.params.id);
      if (!fs.existsSync(dir)) return res.status(404).json({ error: `Dossier candidature introuvable : ${req.params.id}` });
      // Python rend aussi la rubrique « Réalisations en ligne » telle qu'elle
      // s'affiche, même choisie automatiquement : l'éditeur part de là.
      const stdout = await runPython(['-m', 'cv_generator.user_edit', dir, '--show'], {
        timeout: 30000,
        acceptOutputOnError: true,
      });
      const result = JSON.parse(stdout.slice(stdout.indexOf('{')));
      if (!result.ok) return res.status(404).json({ error: result.error || 'Aucun CV généré : lance la génération avant de le modifier.' });
      res.json(result);
    } catch (err) {
      console.error('[GET /applications/:id/cv/edit]', err.message);
      res.status(500).json({ error: err.message });
    }
  });

  router.put('/applications/:id/cv/edit', async (req, res) => {
    const id = req.params.id;
    const dir = applicationDir(id);
    if (!fs.existsSync(dir)) return res.status(404).json({ error: `Dossier candidature introuvable : ${id}` });
    if (hasSendRecord(id)) return res.status(409).json({ error: 'Ce dossier possède déjà une tentative d’envoi ; son CV est verrouillé.' });
    if (!req.body || typeof req.body.cv !== 'object' || Array.isArray(req.body.cv)) {
      return res.status(400).json({ error: 'Corps attendu : { cv: {...} }.' });
    }
    const cvDir = path.join(dir, 'cv');
    const inputPath = path.join(cvDir, `.cv_edit_input.${process.pid}.${Date.now()}.json`);
    try {
      fs.mkdirSync(cvDir, { recursive: true });
      fs.writeFileSync(inputPath, JSON.stringify({ cv: req.body.cv }), 'utf-8');
      const stdout = await runPython(['-m', 'cv_generator.user_edit', dir, '--input', inputPath], {
        timeout: 120000,
        acceptOutputOnError: true,
      });
      const result = JSON.parse(stdout.slice(stdout.indexOf('{')));
      if (!result.ok) return res.status(400).json({ error: result.error || 'Version refusée.' });
      writeApprovalStatus(id, false);
      res.json({ ...statusWithTask(id), approved: false, warnings: result.warnings || [], edited_at: result.edited_at });
    } catch (err) {
      console.error('[PUT /applications/:id/cv/edit]', err.message);
      res.status(500).json({ error: err.message });
    } finally {
      fs.rmSync(inputPath, { force: true });
    }
  });

  router.delete('/applications/:id/cv/edit', async (req, res) => {
    try {
      const id = req.params.id;
      const dir = applicationDir(id);
      if (!fs.existsSync(dir)) return res.status(404).json({ error: `Dossier candidature introuvable : ${id}` });
      if (hasSendRecord(id)) return res.status(409).json({ error: 'Ce dossier possède déjà une tentative d’envoi ; son CV est verrouillé.' });
      await runPython(['-m', 'cv_generator.user_edit', dir, '--reset'], { timeout: 30000 });
      writeApprovalStatus(id, false);
      res.json({ ...statusWithTask(id), approved: false });
    } catch (err) {
      console.error('[DELETE /applications/:id/cv/edit]', err.message);
      res.status(500).json({ error: err.message });
    }
  });

  // POST /api/applications/:id/cv/user-validation — { validated: true|false }
  // Tu valides (ou retires ta validation d')un CV que l'IA a laissé « à
  // corriger ». Un CV « bloqué » ne se valide pas : une affirmation y manque de
  // preuve dans le profil maître. Ce qui partirait change : l'approbation tombe.
  router.post('/applications/:id/cv/user-validation', (req, res) => {
    try {
      const id = req.params.id;
      const dir = applicationDir(id);
      if (!fs.existsSync(dir)) return res.status(404).json({ error: `Dossier candidature introuvable : ${id}` });
      if (typeof req.body?.validated !== 'boolean') {
        return res.status(400).json({ error: 'validated doit valoir true ou false.' });
      }
      if (hasSendRecord(id)) return res.status(409).json({ error: 'Ce dossier possède déjà une tentative d’envoi ; son CV est verrouillé.' });
      const cvDir = path.join(dir, 'cv');
      const validationPath = path.join(cvDir, USER_VALIDATION_FILE);
      if (req.body.validated) {
        const current = cvStatus(id);
        if (current.status === 'blocked') {
          return res.status(409).json({
            error: 'Ce CV est bloqué par le contrôle de véracité : une affirmation n’a pas de preuve dans ton profil maître. Complète le profil ou régénère le CV.',
            cv_status: current.status,
          });
        }
        if (current.status !== 'review') {
          return res.status(409).json({ error: `Rien à valider : le CV est au statut « ${current.status} ».`, cv_status: current.status });
        }
        const pdfPath = path.join(cvDir, USER_VALIDATED_PDF);
        if (!fs.existsSync(pdfPath)) return res.status(409).json({ error: 'Aucun aperçu PDF à valider pour ce CV.' });
        fs.writeFileSync(validationPath, `${JSON.stringify({
          validated_at: new Date().toISOString(),
          cv_status_at_validation: current.status,
          ai_reason: current.reason || '',
          preview_sha256: fileSha256(pdfPath),
        }, null, 2)}\n`, 'utf-8');
      } else if (fs.existsSync(validationPath)) {
        fs.unlinkSync(validationPath);
      }
      writeApprovalStatus(id, false);
      res.json({ ...statusWithTask(id), approved: false });
    } catch (err) {
      console.error('[POST /applications/:id/cv/user-validation]', err.message);
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


  return router;
}
