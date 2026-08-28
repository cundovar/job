---
objective: "Les CV ciblant une mission de formation web et IA présentent un équilibre crédible entre pédagogie, réalisations techniques vérifiables et pratique de l'IA, choisi par les agents IA sans invention ni sélection éditoriale imposée par Python."
status: implemented
---

# Plan: Équilibrer les CV de formateur web et IA

## Overview

| Field      | Value |
| ---------- | ----- |
| **Goal**   | Faire produire et corriger automatiquement un CV hybride qui prouve à la fois la capacité à former et la pratique réelle du développement. |
| **Source** | Demande utilisateur du 28 août 2026, annonce « Formateur(trice) en ligne – Intelligence artificielle et développement web » et `cv_final (22).pdf`. |

## Phases

| #   | Phase | File |
| --- | ----- | ---- |
| 1   | Donner aux agents un contrat éditorial hybride | [`phase-1.md`](./phase-1.md) |
| 2   | Faire juger et corriger la couverture des preuves | [`phase-2.md`](./phase-2.md) |
| 3   | Valider sur l'annonce réelle et préparer le déploiement | [`phase-3.md`](./phase-3.md) |

## Decisions

| Decision | Why |
| -------- | --- |
| Claude choisit les expériences, compétences, formations et projets ; Python ne fait que vérifier leur provenance et le format. | Une règle déterministe ne comprend pas assez finement la différence entre formateur web, formateur généraliste et médiateur numérique. |
| Le CV de formateur web/IA doit couvrir trois piliers : pédagogie, réalisation technique et usage de l'IA. | Le recruteur cherche un praticien capable de transmettre, pas uniquement un formateur ni uniquement un développeur. |
| La présence d'une réalisation publique est un critère du juge IA, jamais l'injection forcée d'un identifiant d'expérience. | Hélène ou La Magicieuse peuvent être choisies selon la stack de l'annonce sans rigidifier le CV. |
| Les lacunes Java, C++ et R restent visibles comme écarts honnêtes et ne sont jamais compensées par du contenu inventé. | L'annonce les demande mais ils ne figurent pas dans la source de vérité du candidat. |
