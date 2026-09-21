---
status: done
---

# Instruction: Composition et regroupement pilotés par les agents

## Architecture projection

> Tree of the final files. ✅ create · ✏️ modify · ❌ delete

```txt
.
├── cv_generator/
│   ├── ✏️ ai_agents.py
│   ├── ✏️ cv_creator.py
│   └── ✏️ job_analyzer.py
├── config/
│   └── ✏️ ai_role_routing.json
└── tests/
    └── ✏️ test_cv_generator.py
```

## User Journey

```mermaid
flowchart TD
  A[Annonce et profil maître] --> B[Agent analyste sélectionne exigences et preuves]
  B --> C[Agent rédacteur choisit expériences projets compétences et ordre]
  C --> D[Agent rédige directement les groupes et leurs puces sourcées]
  D --> E[Python valide sans réécrire]
```

## Test Scope

```mermaid
---
title: Test scope
---
journey
  section Setup
    Fournir une annonce webmaster et des preuves techniques synthétiques => Contexte agent prêt: 5: system
  section Happy path
    L'agent choisit et groupe librement les preuves => Ordre texte et sélection préservés: 5: system
  section Edge case - Omission volontaire
    L'agent retire une expérience planifiée => Expérience non réinjectée par Python: 5: system
  section Edge case - Groupe technique
    L'agent combine trois preuves de deux missions => Trois puces restent visibles et sourcées: 5: system
```

## Tasks to do

### `1)` Rendre le plan IA consultatif

> Le plan propose des preuves sans devenir une liste imposée.

1. Retirer le nombre minimum d'expériences et les réinsertions automatiques.
2. Retirer les préférences métier codées en dur de la sélection Python.
3. Fournir à l'analyste le catalogue complet utile et enregistrer ses justifications.

### `2)` Donner le dernier mot au rédacteur

> Préserver exactement la sélection et l'ordre retournés par l'agent.

1. Supprimer l'ajout automatique d'expériences et de projets absents de la réponse.
2. Ne plus trier les expériences après la réponse; demander et vérifier l'ordre chronologique dans la revue.
3. Ne plus fabriquer de puces de secours lorsqu'une expérience est vide; retourner une erreur de contrat.

### `3)` Remplacer le regroupement déterministe

> Faire des groupes une sortie éditoriale native de l'agent.

1. Autoriser les objets groupés avec `source_experience_ids` et sources par puce.
2. Supprimer la règle « première puce de chaque mission » de `apply_experience_presentation`.
3. Limiter Python à la validation des membres, des sources et des contraintes de longueur.

## Test acceptance criteria

| Task | Acceptance criteria |
| ---- | ------------------- |
| 1 | Une expérience non choisie par l'agent n'apparaît plus dans le CV, même si le plan déterministe la proposait. |
| 2 | Python conserve l'ordre, les compétences et les projets choisis par l'agent sans fallback éditorial. |
| 3 | Le cas CARECO conserve simultanément WooCommerce ou API REST et Twig/Bootstrap/Git dans le groupe La Magicieuse–Qualiscope. |
