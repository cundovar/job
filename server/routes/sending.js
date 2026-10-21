/**
 * routes/sending.js — Envoi d'un dossier : destinataires, approbation, envoi.
 *
 * Extrait de routes/applications.js, sans changement de comportement. L'envoi
 * réel reste fait par applications/send.py, qui refuse tout dossier non approuvé.
 */
import { Router } from 'express';
import fs from 'fs';
import path from 'path';
import { runPython } from '../services/python.js';
import {
  applicationDir,
  readApplicationMetadata,
  rebuildCandidaturesIndex,
  normalizeRecipients,
  effectiveRecipients,
  hasSendRecord,
  writeApprovalStatus,
  cleanAttachmentName,
  approvalState,
  cvBlocksSending,
  MAX_SEND_RECIPIENTS,
  DEFAULT_ATTACHMENT_NAMES,
  READY_STATUS,
} from '../services/applicationFiles.js';

export default function createSendingRouter() {
  const router = Router();

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
      // send.py sort en erreur pour un dossier refusé tout en écrivant son
      // rapport JSON : la sortie compte, pas le code de retour.
      const stdout = await runPython(args, { timeout: 120000, acceptOutputOnError: true });
      if (!stdout) throw new Error('sortie vide');
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
      await rebuildCandidaturesIndex();
      res.json({ ok: true, adresse: email });
    } catch (err) {
      console.error('[POST /applications/:id/contact]', err.message);
      res.status(500).json({ error: err.message });
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

  // GET /api/applications/:id/recipients — Liste effective To/Cc du dossier.
  router.get('/applications/:id/recipients', (req, res) => {
    try {
      const dir = applicationDir(req.params.id);
      if (!fs.existsSync(dir)) return res.status(404).json({ error: `Dossier candidature introuvable : ${req.params.id}` });
      const metadata = readApplicationMetadata(req.params.id);
      res.json({ recipients: effectiveRecipients(req.params.id, metadata), max: MAX_SEND_RECIPIENTS });
    } catch (err) {
      res.status(400).json({ error: err.message });
    }
  });

  // PUT /api/applications/:id/recipients — Remplace atomiquement la sélection To/Cc.
  router.put('/applications/:id/recipients', (req, res) => {
    try {
      const dir = applicationDir(req.params.id);
      if (!fs.existsSync(dir)) return res.status(404).json({ error: `Dossier candidature introuvable : ${req.params.id}` });
      if (hasSendRecord(req.params.id)) return res.status(409).json({ error: 'Ce dossier possède déjà une tentative d’envoi ; ses destinataires sont verrouillés.' });
      const recipients = normalizeRecipients(req.body?.recipients);
      const metadataPath = path.join(dir, 'metadata.json');
      const metadata = readApplicationMetadata(req.params.id);
      metadata.send_recipients = recipients;
      metadata.status = READY_STATUS;
      metadata.approval_updated_at = new Date().toISOString();
      delete metadata.approval_recipients_hash;
      const temporaryPath = `${metadataPath}.${process.pid}.tmp`;
      fs.writeFileSync(temporaryPath, `${JSON.stringify(metadata, null, 2)}\n`, 'utf-8');
      fs.renameSync(temporaryPath, metadataPath);
      res.json({ ok: true, recipients, approved: false });
    } catch (err) {
      res.status(400).json({ error: err.message });
    }
  });

  // PUT /api/applications/:id/send-options — Joindre ou non la lettre.
  // La lettre reste dans le dossier : on choisit ce qui part, on ne supprime
  // rien. Comme pour les destinataires, changer ce qui partira retire
  // l'approbation : on approuve un envoi précis, pas une intention.
  router.put('/applications/:id/send-options', (req, res) => {
    try {
      const dir = applicationDir(req.params.id);
      if (!fs.existsSync(dir)) return res.status(404).json({ error: `Dossier candidature introuvable : ${req.params.id}` });
      if (hasSendRecord(req.params.id)) return res.status(409).json({ error: 'Ce dossier possède déjà une tentative d’envoi ; ses pièces jointes sont verrouillées.' });
      if (typeof req.body?.include_lettre !== 'boolean') {
        return res.status(400).json({ error: 'include_lettre doit valoir true ou false.' });
      }
      const metadataPath = path.join(dir, 'metadata.json');
      const metadata = readApplicationMetadata(req.params.id);
      metadata.send_include_lettre = req.body.include_lettre;
      metadata.status = READY_STATUS;
      metadata.approval_updated_at = new Date().toISOString();
      delete metadata.approval_recipients_hash;
      const temporaryPath = `${metadataPath}.${process.pid}.tmp`;
      fs.writeFileSync(temporaryPath, `${JSON.stringify(metadata, null, 2)}\n`, 'utf-8');
      fs.renameSync(temporaryPath, metadataPath);
      res.json({ ok: true, include_lettre: metadata.send_include_lettre, approved: false });
    } catch (err) {
      res.status(400).json({ error: err.message });
    }
  });

  // PUT /api/applications/:id/attachment-names — { cv, lettre }
  // Nom des fichiers PDF, au téléchargement comme en pièce jointe. Vide = nom
  // par défaut. Le nom vu par le destinataire change : l'approbation tombe.
  router.put('/applications/:id/attachment-names', (req, res) => {
    try {
      const dir = applicationDir(req.params.id);
      if (!fs.existsSync(dir)) return res.status(404).json({ error: `Dossier candidature introuvable : ${req.params.id}` });
      if (hasSendRecord(req.params.id)) return res.status(409).json({ error: 'Ce dossier possède déjà une tentative d’envoi ; ses pièces jointes sont verrouillées.' });
      const names = { cv: cleanAttachmentName(req.body?.cv), lettre: cleanAttachmentName(req.body?.lettre) };
      const metadataPath = path.join(dir, 'metadata.json');
      const metadata = readApplicationMetadata(req.params.id);
      const kept = Object.fromEntries(Object.entries(names).filter(([, value]) => value));
      if (Object.keys(kept).length) metadata.attachment_names = kept;
      else delete metadata.attachment_names;
      metadata.status = READY_STATUS;
      metadata.approval_updated_at = new Date().toISOString();
      delete metadata.approval_recipients_hash;
      const temporaryPath = `${metadataPath}.${process.pid}.tmp`;
      fs.writeFileSync(temporaryPath, `${JSON.stringify(metadata, null, 2)}\n`, 'utf-8');
      fs.renameSync(temporaryPath, metadataPath);
      res.json({ ok: true, attachment_names: names, default_attachment_names: DEFAULT_ATTACHMENT_NAMES, approved: false });
    } catch (err) {
      console.error('[PUT /applications/:id/attachment-names]', err.message);
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
      if (approved && hasSendRecord(req.params.id)) {
        return res.status(409).json({ error: 'Ce dossier possède déjà une tentative d’envoi.' });
      }
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

  return router;
}
