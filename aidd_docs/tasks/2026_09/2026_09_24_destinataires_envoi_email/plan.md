---
objective: "Permettre de gérer une ou plusieurs adresses destinataires par dossier, avec remplacement ou ajout d'adresses existantes, tout en conservant l'approbation séparée de l'envoi réel et la règle d'un seul envoi par dossier."
status: in-progress
---

# Plan: Destinataires multiples pour l'envoi email

## Overview

| Field      | Value                   |
| ---------- | ----------------------- |
| **Goal**   | Donner à l'utilisateur le contrôle explicite de la liste des destinataires Brevo avant l'envoi. |
| **Source** | Demande utilisateur du 24/09/2026 et flux actuel de `front/src/App.jsx`, `server/routes/applications.js` et `applications/send.py`. |

## Phases

| #   | Phase        | File                         |
| --- | ------------ | ---------------------------- |
| 1   | Contrat destinataires et sécurité d'envoi | [`phase-1.md`](./phase-1.md) |
| 2   | Interface de gestion des destinataires | [`phase-2.md`](./phase-2.md) |
| 3   | Tests et vérification de non-régression | [`phase-3.md`](./phase-3.md) |

## Decisions

| Decision | Why |
| -------- | --- |
| Conserver les adresses prouvées dans `job.json` et enregistrer la liste effectivement choisie dans `metadata.json`. | Une adresse détectée et une adresse choisie pour un envoi sont deux notions différentes ; cela évite de falsifier la preuve de prospection et permet un remplacement par dossier. |
| Limiter chaque dossier à 5 destinataires : le premier en `To`, les suivants en `Cc`, dans une seule requête Brevo. | La limite couvre le besoin métier, garde les destinataires visibles et respecte la règle « un seul envoi par dossier ». |
| Pour un ancien dossier sans sélection persistée, conserver uniquement la première adresse historiquement utilisée. | La migration ne doit pas élargir silencieusement le nombre de personnes contactées. Les autres adresses pourront être ajoutées explicitement depuis l'interface. |
| Toute modification de la liste invalide l'approbation, et l'approbation enregistre l'empreinte de la liste exacte. | Le pipeline d'envoi peut ainsi refuser une liste différente de celle validée, même si un fichier est modifié hors de l'endpoint prévu. |
| Bloquer toute nouvelle tentative après un envoi réussi ou échoué déjà journalisé, conformément à la protection actuelle. | Ajouter des destinataires ne doit pas créer un contournement de la déduplication et du « un seul envoi ». |
| Maintenir l'accusé interne `BREVO_CONFIRM_TO` comme un envoi séparé vers un seul destinataire. | L'évolution de l'envoi principal ne doit pas transformer l'accusé interne en message multi-destinataires. |
| Ajouter Vitest et React Testing Library au frontend. | Le frontend ne possède actuellement aucun harnais de test ; le parcours d'édition et de réapprobation doit être vérifiable automatiquement. |

## Resources

| Source | Verified |
| ------ | -------- |
| https://developers.brevo.com/reference/send-transac-email | Le payload transactionnel Brevo accepte plusieurs destinataires dans `to` et dans `cc`; le projet applique sa propre limite de 5. |
