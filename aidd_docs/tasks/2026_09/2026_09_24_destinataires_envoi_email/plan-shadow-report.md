---
source: aidd_docs/tasks/2026_09/2026_09_24_destinataires_envoi_email/plan.md
generated_at: 2026-09-24
---

# Shadow Areas Report

Source: `aidd_docs/tasks/2026_09/2026_09_24_destinataires_envoi_email/plan.md` et ses trois phases
Generated: `2026-09-24`

Total gaps: 8 | Blocker: 0 | Major: 7 | Minor: 1

---

## Gaps by Category

### unstated assumption

**[major]** Does approval record a fingerprint of the exact recipient list so that the send command can reject any list changed after approval?
> Toute modification de la liste des destinataires invalide l'approbation courante.

**[major]** Should multiple recipients be placed together in `To`, or should secondary recipients use `Cc` or `Bcc` to control address visibility?
> Envoyer plusieurs destinataires dans une seule requête Brevo avec un tableau `to`.

### ambiguous term

**[major]** Which legacy behavior wins when several proven addresses exist: selecting only the first address or importing all proven addresses?
> Définir la migration implicite pour les anciens dossiers : reprendre toutes les adresses prouvées, avec la première adresse comme comportement de compatibilité.

### missing edge case

**[major]** What should happen when new proven addresses appear in `job.json` after a recipient selection has already been saved in `metadata.json`?
> Remplacer l'extraction mono-adresse par une extraction multi-adresses, puis prioriser la sélection persistée.

### missing actor

**[major]** How will the separate confirmation email sent to `BREVO_CONFIRM_TO` remain a single-recipient message after the sender interface becomes multi-recipient?
> Adapter `EmailSender`, SMTP et Brevo au tableau de destinataires.

### missing failure mode

**[major]** How will the tracker represent and report a mixed delivery outcome when Brevo accepts one request but later delivers to only some recipients?
> Journaliser la liste complète dans le tracker et conserver la protection contre un second envoi.

### missing acceptance criterion

**[major]** What exact maximum number of recipients must the API accept per dossier?
> Valider côté serveur les formats, doublons, nombre maximal et présence d'au moins un destinataire.

### missing dependency

**[minor]** Which frontend test harness and command will verify the browser journey, given that `front/package.json` currently defines no test dependency or test script?
> front/src/App.test.* ou tests/e2e/*   ✅ créer selon le harnais frontend existant

