/**
 * services/applicationFiles.js — Lecture et écriture des dossiers de candidature.
 *
 * Fonctions partagées par les routes candidatures et envoi : chemin d'un
 * dossier, statut du CV, métadonnées, destinataires, approbation, noms des
 * pièces jointes. Extraites de routes/applications.js, sans changement.
 */
import fs from 'fs';
import crypto from 'crypto';
import path from 'path';
import { PROJECT_ROOT } from '../config.js';
import { runPython } from './python.js';
import {
  CV_FILES,
  resolveCvPublication,
  USER_VALIDATION_FILE,
  USER_VALIDATED_PDF,
} from './cvPublication.js';

const MAX_CV_PROCESS_OUTPUT = 10 * 1024 * 1024;
const CV_PYTHON_BIN = process.env.CV_PYTHON_BIN || 'python3';
const CV_TASK_TIMEOUT_MS = Number.parseInt(
  process.env.CV_TASK_TIMEOUT_MS || String(15 * 60 * 1000),
  10
);
const CV_TASK_KILL_GRACE_MS = 5000;
const CV_TASK_RETENTION_MS = 60 * 60 * 1000;
const PREPARE_TASK_RETENTION_MS = 60 * 60 * 1000;
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

// Le front lit les lettres et les mails dans `front/public/data/candidatures.json`,
// pas dans le dossier de candidature : tant que cet index n'est pas reconstruit,
// une édition enregistrée sur disque réapparaît à l'ancienne au rechargement.
function rebuildCandidaturesIndex() {
  return runPython(
    ['-c', "from applications.candidatures_index import rebuild_candidatures_index as r; print(r('output/applications', 'front/public/data/candidatures.json'))"],
    { timeout: 60000 }
  );
}

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
  const publication = resolveCvPublication(files, assessment, review, readUserValidation(cvDir));
  return { exists: fs.existsSync(cvDir), files, review, assessment, progress, ...publication };
}

function fileSha256(filePath) {
  return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}

// Validation humaine : valide seulement si l'aperçu n'a pas changé depuis.
function readUserValidation(cvDir) {
  const validationPath = path.join(cvDir, USER_VALIDATION_FILE);
  const pdfPath = path.join(cvDir, USER_VALIDATED_PDF);
  if (!fs.existsSync(validationPath) || !fs.existsSync(pdfPath)) return null;
  try {
    const validation = JSON.parse(fs.readFileSync(validationPath, 'utf-8'));
    return { ...validation, valid: validation?.preview_sha256 === fileSha256(pdfPath) };
  } catch {
    return null;
  }
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

const CONTACT_RE = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const MAX_SEND_RECIPIENTS = 5;

function normalizeRecipients(raw) {
  if (!Array.isArray(raw)) throw new Error('La liste des destinataires doit être un tableau.');
  if (raw.length < 1 || raw.length > MAX_SEND_RECIPIENTS) {
    throw new Error(`La liste doit contenir entre 1 et ${MAX_SEND_RECIPIENTS} destinataires.`);
  }
  const recipients = raw.map((item, index) => {
    const email = String(typeof item === 'string' ? item : item?.email || '').trim().toLowerCase();
    const role = String(typeof item === 'string' ? (index === 0 ? 'to' : 'cc') : item?.role || (index === 0 ? 'to' : 'cc')).toLowerCase();
    if (!/^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(email)) {
      throw new Error(`Adresse email invalide : ${email || '(vide)'}`);
    }
    if (!['to', 'cc'].includes(role)) throw new Error('Le rôle destinataire doit être « to » ou « cc ».');
    return { email, role, source: String(typeof item === 'object' ? item?.source || 'selection' : 'ajout_manuel') };
  });
  // Un envoi part à une adresse, les autres sont en copie. Le message dit
  // laquelle des deux situations on a sous les yeux : « exactement un » laissait
  // croire qu'il manquait une adresse alors qu'il manquait un rôle.
  const principaux = recipients.filter(item => item.role === 'to').length;
  if (principaux === 0) {
    throw new Error('Aucun destinataire principal : passe une des adresses en « To ».');
  }
  if (principaux > 1) {
    throw new Error(`Un seul destinataire principal « To » est possible (${principaux} ici) — les autres passent en « Cc ».`);
  }
  if (new Set(recipients.map(item => item.email)).size !== recipients.length) {
    throw new Error('Une même adresse ne peut apparaître qu’une seule fois.');
  }
  return recipients;
}

function recipientFingerprint(recipients) {
  const canonical = recipients.map(({ email, role }) => ({ email, role }));
  return crypto.createHash('sha256').update(JSON.stringify(canonical)).digest('hex');
}

function publicContactRecipients(id) {
  try {
    const job = JSON.parse(fs.readFileSync(path.join(applicationDir(id), 'job.json'), 'utf-8'));
    const seen = new Set();
    const contacts = [];
    for (const claim of Array.isArray(job.public_contact) ? job.public_contact : []) {
      const texts = [claim?.claim, ...(Array.isArray(claim?.evidence) ? claim.evidence : [])].map(String);
      for (const text of texts) {
        for (const match of text.matchAll(CONTACT_RE)) {
          const email = match[0].toLowerCase();
          if (!seen.has(email)) {
            seen.add(email);
            contacts.push({ email, role: contacts.length === 0 ? 'to' : 'cc', source: text });
          }
        }
      }
    }
    return contacts.slice(0, 1);
  } catch {
    return [];
  }
}

function effectiveRecipients(id, metadata = readApplicationMetadata(id)) {
  const raw = Array.isArray(metadata.send_recipients) && metadata.send_recipients.length
    ? metadata.send_recipients
    : publicContactRecipients(id);
  return normalizeRecipients(raw);
}

function hasSendRecord(id) {
  const trackerPath = path.resolve(PROJECT_ROOT, 'data/applications_tracker.json');
  try {
    const records = JSON.parse(fs.readFileSync(trackerPath, 'utf-8'));
    return Object.values(records || {}).some(record =>
      path.resolve(String(record.application_dir || '')) === applicationDir(id)
      && ['applied', 'send_failed'].includes(record.status)
    );
  } catch {
    return false;
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
  if (approved) {
    const recipients = effectiveRecipients(id, metadata);
    metadata.approval_recipients_hash = recipientFingerprint(recipients);
  } else {
    delete metadata.approval_recipients_hash;
  }
  const temporaryPath = `${metadataPath}.${process.pid}.tmp`;
  fs.writeFileSync(temporaryPath, `${JSON.stringify(metadata, null, 2)}\n`, 'utf-8');
  fs.renameSync(temporaryPath, metadataPath);
  return metadata;
}

// Adresses écrites dans le texte d'une annonce (« envoyez votre CV à … »).
// Ce ne sont que des suggestions : rien n'est sélectionné sans un clic, et
// chaque adresse garde l'extrait d'où elle vient.
function announcementEmailSuggestions(id, recipients = []) {
  try {
    const job = JSON.parse(fs.readFileSync(path.join(applicationDir(id), 'job.json'), 'utf-8'));
    const text = String(job.description || '');
    const taken = new Set(recipients.map(item => item.email));
    const suggestions = [];
    for (const match of text.matchAll(CONTACT_RE)) {
      const email = match[0].toLowerCase();
      if (taken.has(email)) continue;
      taken.add(email);
      const start = Math.max(0, match.index - 60);
      const extrait = text.slice(start, match.index + match[0].length + 20).replace(/\s+/g, ' ').trim();
      suggestions.push({ email, source: `texte de l’annonce : « ${extrait} »` });
      if (suggestions.length >= 5) break;
    }
    return suggestions;
  } catch {
    return [];
  }
}

// Noms des fichiers PDF choisis par le candidat. Même règle que
// applications/send.py (clean_attachment_name) : pas de séparateur de chemin
// ni de caractère interdit, 120 caractères au plus, toujours en .pdf.
const DEFAULT_ATTACHMENT_NAMES = {
  cv: 'CV - Facundo Varas.pdf',
  lettre: 'Lettre de motivation - Facundo Varas.pdf',
};

function cleanAttachmentName(value) {
  let name = String(value ?? '').replace(/[\\/:*?"<>|\u0000-\u001f]/g, ' ').replace(/\s+/g, ' ').trim();
  if (name.toLowerCase().endsWith('.pdf')) name = name.slice(0, -4);
  name = name.replace(/^[\s.]+|[\s.]+$/g, '').slice(0, 116).replace(/^[\s.]+|[\s.]+$/g, '');
  return name ? `${name}.pdf` : '';
}

function customAttachmentNames(metadata) {
  const raw = metadata?.attachment_names && typeof metadata.attachment_names === 'object' ? metadata.attachment_names : {};
  return { cv: cleanAttachmentName(raw.cv), lettre: cleanAttachmentName(raw.lettre) };
}

function approvalState(id) {
  const metadata = readApplicationMetadata(id);
  let recipients = [];
  try { recipients = effectiveRecipients(id, metadata); } catch { recipients = []; }
  return {
    suggestions: announcementEmailSuggestions(id, recipients),
    id,
    status: metadata.status || '',
    approved: metadata.status === APPROVED_STATUS,
    approval_updated_at: metadata.approval_updated_at || null,
    recipients,
    recipients_hash: metadata.approval_recipients_hash || null,
    // Clé absente = la lettre part, comme tous les dossiers l'ont toujours fait.
    include_lettre: metadata.send_include_lettre !== false,
    attachment_names: customAttachmentNames(metadata),
    default_attachment_names: DEFAULT_ATTACHMENT_NAMES,
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

// Un dossier sans CV garde le flux d'avant : le CV est optionnel. Un dossier
// avec un CV refusé bloque, en disant pourquoi.
function cvBlocksSending(id) {
  let publication;
  try {
    publication = cvStatus(id);
  } catch {
    return null;
  }
  if (['absent', 'ready', 'validated', 'uploaded'].includes(publication.status)) return null;
  return {
    error: "Le CV de cette candidature n'est pas validé.",
    cv_status: publication.status,
    reason: publication.reason,
  };
}

export {
  MAX_CV_PROCESS_OUTPUT,
  CV_PYTHON_BIN,
  CV_TASK_TIMEOUT_MS,
  CV_TASK_KILL_GRACE_MS,
  CV_TASK_RETENTION_MS,
  PREPARE_TASK_RETENTION_MS,
  APPROVED_STATUS,
  READY_STATUS,
  REQUIRED_FRESH_CV_FILES,
  rebuildCandidaturesIndex,
  applicationDir,
  cvStatus,
  fileSha256,
  readUserValidation,
  readApplicationMetadata,
  CONTACT_RE,
  MAX_SEND_RECIPIENTS,
  normalizeRecipients,
  recipientFingerprint,
  publicContactRecipients,
  effectiveRecipients,
  hasSendRecord,
  writeApprovalStatus,
  announcementEmailSuggestions,
  DEFAULT_ATTACHMENT_NAMES,
  cleanAttachmentName,
  customAttachmentNames,
  approvalState,
  cvCatalogEntry,
  hasFreshCvOutputs,
  publicCvTask,
  cvBlocksSending,
};
