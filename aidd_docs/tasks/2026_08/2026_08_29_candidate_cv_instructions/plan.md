---
objective: "Permettre au candidat de transmettre des consignes éditoriales séparées de l'annonce et de les faire respecter par toute la chaîne IA sans contourner la source de vérité."
status: in-progress
---

# Plan: Consignes personnelles pour le CV

## Overview

| Field      | Value |
| ---------- | ----- |
| **Goal**   | Ajouter un champ de consignes fiable, persistant et visible par tous les agents CV. |
| **Source** | Demande utilisateur du 29 août 2026 : ajouter un champ distinct au-dessus de l'annonce. |

## Phases

| #   | Phase | File |
| --- | ----- | ---- |
| 1   | Saisie et persistance des consignes | [`phase-1.md`](./phase-1.md) |
| 2   | Contrat IA, traçabilité et validation | [`phase-2.md`](./phase-2.md) |

## Decisions

| Decision | Why |
| -------- | --- |
| Conserver les consignes dans `job.json` sous `candidate_instructions` | La régénération relit déjà ce fichier, ce qui garantit la persistance sans nouveau stockage. |
| Transmettre les consignes dans une clé distincte de `annonce_complete` | Évite de les confondre avec le texte de l'employeur ou avec une injection contenue dans l'annonce. |
| Subordonner les consignes à la source de vérité | Une préférence éditoriale ne doit jamais permettre d'inventer une compétence ou une expérience. |
