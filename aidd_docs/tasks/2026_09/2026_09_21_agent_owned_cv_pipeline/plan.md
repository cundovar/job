---
objective: "Les agents IA décident seuls du contenu éditorial du CV tandis que Python valide la vérité, le format et le droit d'exporter sans réécrire leurs choix."
status: pending
---

# Plan: Pipeline CV piloté par les agents IA

## Overview

| Field      | Value |
| ---------- | ----- |
| **Goal**   | Remplacer le générateur éditorial hybride par une chaîne où les agents composent et révisent le CV, et où Python se limite aux garde-fous non modificatifs. |
| **Source** | Demande utilisateur du 21/09/2026, motivée par le CV CARECO qui perd les preuves WooCommerce, API REST, Twig, Bootstrap et Git après composition IA. |

## Phases

| # | Phase | File |
| - | ----- | ---- |
| 1 | Contrat de provenance et validations non modificatrices | [`phase-1.md`](./phase-1.md) |
| 2 | Composition et regroupement entièrement pilotés par les agents | [`phase-2.md`](./phase-2.md) |
| 3 | Double vérification, révisions bornées et verrou d'export | [`phase-3.md`](./phase-3.md) |
| 4 | Propagation des statuts dans l'API et le frontend | [`phase-4.md`](./phase-4.md) |
| 5 | Non-régression CARECO et assainissement des anciens garde-fous | [`phase-5.md`](./phase-5.md) |

## Decisions

| Decision | Why |
| -------- | --- |
| Python valide et refuse, mais ne complète, ne réordonne et ne reformule jamais le contenu éditorial. | Empêcher qu'une transformation déterministe annule une décision pertinente d'un agent tout en conservant la source de vérité. |
| Chaque affirmation éditoriale porte des références explicites vers le profil maître. | Rendre la véracité vérifiable sans reconstruire le texte à partir de règles Python. |
| Les expériences groupées sont des objets rédigés par l'agent avec des sources par puce. | Éviter le comportement actuel qui ne conserve que la première puce de chaque expérience. |
| Une revue encore à `needs_revision` interdit les artefacts `cv_final.*`. | Ne plus présenter comme final un CV que le propre juge du pipeline refuse. |
| Trois révisions au maximum, avec arrêt anticipé sur validation ou absence de progrès. | Donner au réviseur une vraie capacité de correction sans créer une boucle coûteuse ou infinie. |
| Les anciens champs restent lisibles pendant une migration courte, mais ne pilotent plus les choix éditoriaux. | Permettre une livraison progressive sans casser les dossiers existants. |
