---
objective: "Le bouton Retenir et préparer lance la candidature agence en arrière-plan et reste fiable malgré une génération longue."
status: in-progress
---

# Plan: Préparation agence asynchrone

## Overview

| Field | Value |
| --- | --- |
| **Goal** | Remplacer la requête longue `/api/agencies/target` par une tâche suivie par polling. |
| **Source** | Diagnostic confirmé avec l'utilisateur le 19 septembre 2026. |

## Phases

| # | Phase | File |
| --- | --- | --- |
| 1 | File backend, suivi frontend et non-régression | [`phase-1.md`](./phase-1.md) |

## Decisions

| Decision | Why |
| --- | --- |
| Répondre immédiatement en HTTP 202 | La mesure et le CV peuvent dépasser plusieurs minutes. |
| Conserver une seule tâche active par domaine | Un double clic ou une relance ne doit pas dupliquer le travail. |
| Tolérer les erreurs réseau transitoires pendant le polling | Le parcours doit rester fiable sur mobile et après une brève coupure. |
| Préserver le mode `dry` synchrone | Il ne lance aucun traitement long et reste utile au diagnostic. |
