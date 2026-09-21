---
status: done
---

# Instruction: Double vérification, révisions bornées et verrou d'export

## Architecture projection

> Tree of the final files. ✅ create · ✏️ modify · ❌ delete

```txt
.
├── cv_generator/
│   ├── ✏️ ai_agents.py
│   ├── ✏️ pipeline.py
│   ├── ✏️ exporters.py
│   └── ✏️ ats_exporter.py
├── config/
│   └── ✏️ ai_role_routing.json
└── tests/
    └── ✏️ test_cv_generator.py
```

## User Journey

```mermaid
flowchart TD
  A[CV rédigé] --> B[Vérificateur de vérité]
  B -->|erreurs| E[Agent réviseur]
  B -->|valide| C[Agent recruteur]
  C -->|needs revision| E
  E --> B
  C -->|validated| D[Export final]
  E -->|trois échecs ou absence de progrès| F[État review sans fichier final]
```

## Test Scope

```mermaid
---
title: Test scope
---
journey
  section Setup
    Injecter des agents simulés et un profil synthétique => Pipeline isolé: 5: system
  section Happy path
    Corriger un CV puis obtenir validated => PDF final exporté après deux contrôles: 5: system
  section Edge case - Révision persistante
    Rester needs_revision après trois passages => Aucun cv_final publié et statut review: 1: system
  section Edge case - Boucle stagnante
    Renvoyer deux fois le même contenu et les mêmes problèmes => Arrêt anticipé avec cause tracée: 5: system
```

## Tasks to do

### `1)` Séparer vérité et pertinence

> Éviter qu'un score éditorial masque une erreur factuelle.

1. Faire exécuter le validateur Python avant tout jugement éditorial.
2. Ajouter un agent vérificateur de vérité qui peut uniquement accepter ou refuser les affirmations sourcées.
3. Conserver le juge recruteur pour pertinence, lisibilité, couverture et ATS.

### `2)` Piloter les corrections

> Donner au réviseur toutes les erreurs actionnables.

1. Fusionner les erreurs de vérité, de pertinence et de rendu dans un contrat de correction unique.
2. Autoriser trois révisions maximum avec arrêt dès `validated`.
3. Détecter l'absence de progrès par empreinte du contenu et des problèmes.

### `3)` Verrouiller l'export final

> Ne publier que les CV réellement acceptés.

1. Produire les JSON de diagnostic à chaque passage.
2. Réserver `cv_final.html`, `cv_final.pdf` et `cv_ats.pdf` au statut `ready`.
3. En cas de révision persistante, produire au plus des artefacts explicitement nommés `cv_review_preview.*`.

## Test acceptance criteria

| Task | Acceptance criteria |
| ---- | ------------------- |
| 1 | Une invention bloque avant le juge recruteur et une faiblesse éditoriale n'altère jamais les données sources. |
| 2 | Le pipeline effectue jusqu'à trois corrections, s'arrête sur validation et trace chaque passage. |
| 3 | Aucun fichier portant `cv_final` n'est créé ou remplacé lorsque le dernier verdict reste `needs_revision`. |
