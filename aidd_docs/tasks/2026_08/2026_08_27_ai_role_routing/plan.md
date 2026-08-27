---
objective: "Chaque rôle IA utilise un fournisseur, un modèle et un niveau de raisonnement dédiés, avec des secours ordonnés et les garde-fous existants préservés."
status: implemented
---

# Plan: Routage IA par rôle

## Source

Demande utilisateur du 27 août 2026, avec matrice de rôles approuvée et Claude Opus 5 imposé pour le juge qualité et la lettre de motivation.

## Phases

| # | Phase | File |
| --- | --- | --- |
| 1 | Transport du modèle et du niveau de raisonnement dans le bridge | [`phase-1.md`](./phase-1.md) |
| 2 | Routage ordonné des agents d’annonce, de CV et de lettre | [`phase-2.md`](./phase-2.md) |
| 3 | Tests de repli, traçabilité et documentation | [`phase-3.md`](./phase-3.md) |

## Matrice cible

| Rôle | Principal | Secours 1 | Secours 2 |
| --- | --- | --- | --- |
| Filtrage des annonces | DeepSeek | Codex faible | Claude Sonnet |
| Analyse approfondie et sélection des expériences | Claude Sonnet | Codex moyen | DeepSeek |
| Rédaction du CV | Codex Sol moyen | Claude Sonnet | DeepSeek |
| Juge qualité | Claude Opus 5 | Codex Sol élevé | DeepSeek |
| Correction finale | Codex Sol moyen | Claude Sonnet | DeepSeek |
| Lettre de motivation | Claude Opus 5 | Codex Sol moyen | DeepSeek |
| Résumé et mail standard | Python | — | — |

## Décisions

- Le routage est déterministe par nom d’agent.
- Un échec technique ou une réponse invalide déclenche le fournisseur suivant.
- Les contrôles Python de véracité et de structure restent obligatoires après chaque réponse IA.
- Les modèles restent surchargeables par variables d’environnement.
- L’alias Claude CLI `opus` représente l’Opus le plus récent disponible sur l’abonnement ; il est utilisé pour Opus 5.

## Critères d’acceptation

- Chaque appel au bridge peut transmettre un modèle et un niveau de raisonnement autorisés.
- Chaque agent suit exactement l’ordre principal/secours défini dans la matrice.
- DeepSeek reste utilisable directement depuis le conteneur.
- Une indisponibilité du principal provoque automatiquement le repli suivant.
- Les traces indiquent le fournisseur et le modèle réellement utilisés.
- Les tests existants et les nouveaux tests de routage passent.
