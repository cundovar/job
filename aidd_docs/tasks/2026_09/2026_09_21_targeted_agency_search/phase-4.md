---
status: pending
---

# Instruction: Mode ville générique de bout en bout

## Architecture projection

> Tree of the final files. ✅ create · ✏️ modify · ❌ delete

```txt
.
├── tools/
│   └── ✏️ agency_prospecting_v2.py
├── server/
│   ├── ✏️ routes/applications.js
│   └── ✏️ services/agenciesService.js
├── ✏️ hermes_mcp_server.py
├── docs/
│   └── ✏️ AGENCIES_SCHEMA.md
└── tests/
    ├── ✏️ test_agency_prospecting.py
    ├── ✏️ test_hermes_mcp_server.py
    └── ✏️ test_deployment_contract.py
```

## User Journey

```mermaid
flowchart TD
  A[Demander agences à Montreuil] --> B[agency_search ville Montreuil]
  B --> C[Résoudre commune code postal code INSEE coordonnées]
  C --> D[Générer requêtes et filtres dynamiques]
  D --> E[Répondre 202 avec task_id]
  E --> F[agency_status suit les étapes]
  F --> G[agency_list lit la recherche terminée]
```

## Test Scope

```mermaid
---
title: Test scope
---
journey
  section Setup
    Simuler résolution Montreuil et Lille => communes distinctes et stables: 5: system
  section Happy path
    Lancer ville Montreuil => requêtes dynamiques et filtre 93100 dans une tâche asynchrone: 5: api
    Suivre puis lister => résultats issus du search_id terminé: 5: api
  section Edge case - homonyme
    Demander une ville ambiguë => choix explicite requis avec département: 5: api
  section Edge case - ville inconnue
    Résolution sans correspondance => erreur avec exemples et aucune recherche de repli: 5: api
  section Edge case - concurrence
    Lancer deux villes différentes => deux tâches ordonnées sans réutilisation croisée: 5: api
```

## Tasks to do

### `1)` Résoudre une ville sans catalogue interne

> Transformer un libellé utilisateur en périmètre géographique stable.

1. Ajouter `--ville` mutuellement exclusif avec `--zone`.
2. Résoudre nom, département, code postal, code INSEE et coordonnées via une source publique ; exiger le département en cas d'homonymie.
3. Construire dynamiquement deux familles conservées jusqu'au résultat : agence web/WordPress/développement et formation numérique/RGAA/web.
4. Filtrer en priorité sur l'adresse vérifiée et le code commune, jamais seulement sur la présence du nom dans une page.

### `2)` Propager la ville dans Node et MCP

> Rendre « trouve-moi des agences à Montreuil » directement exprimable.

1. Accepter `city` dans `POST /api/agencies/search` et dans l'outil `agency_search`.
2. Inclure la ville résolue dans la clé de déduplication, le statut et le `search_id`.
3. Faire retourner `search_id` à `agency_status`, puis le consommer par `agency_list`.
4. Conserver `zone` pour compatibilité pendant la migration, sans ajouter de nouvelles villes dans `ZONES`.

### `3)` Réduire le temps du parcours ciblé

> Favoriser les résultats locaux fiables avant le crawl large.

1. Interroger le registre officiel et les moteurs comme sources complémentaires avec les deux familles de requêtes de la ville.
2. Limiter le crawl approfondi aux candidats locaux dédoublonnés et présélectionnés par les exclusions du barème corrigé, sans faire du registre un juge métier.
3. Publier des étapes de progression séparées : résolution, registre, découverte web, crawl, géocodage, IA, publication.
4. Mesurer durées et volumes par étape dans le payload sans journaliser de données personnelles.

### `4)` Supprimer la nécessité d'étendre les zones statiques

> Garder les anciennes zones seulement comme préréglages compatibles.

1. Documenter que `ZONES` représente des préréglages historiques, pas la liste des villes supportées.
2. Tester Montreuil et Lille pour prouver le fonctionnement IDF et hors IDF.
3. Vérifier qu'une ville nouvelle fonctionne sans modification du code source.

## Test acceptance criteria

| Task | Acceptance criteria |
| ---- | ------------------- |
| 1 | `--ville Montreuil` résout 93100/93066 et `--ville Lille` résout son propre périmètre, sans entrée ajoutée dans `ZONES` et sans perdre les résultats `formation`. |
| 2 | Hermes lance, suit et relit une recherche par ville sans confondre deux tâches de villes différentes. |
| 3 | Le statut expose les étapes et le crawl profond ne traite que les candidats appartenant au périmètre vérifié. |
| 4 | Une fixture de ville absente du code produit des requêtes et un résultat historisé sans modification d'une constante de communes. |
