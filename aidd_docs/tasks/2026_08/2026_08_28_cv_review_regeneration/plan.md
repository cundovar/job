---
objective: "Fiabiliser les CV de formateur technique, exposer le jugement IA et la régénération dans l'interface, et centrer les contenus courts."
status: implemented
---

# Plan: CV formateur, jugement visible et régénération

## Phases

| # | Phase | File |
|---|---|---|
| 1 | Preuves obligatoires du formateur technique | [`phase-1.md`](./phase-1.md) |
| 2 | Verdict final, discussion IA et régénération | [`phase-2.md`](./phase-2.md) |
| 3 | Centrage vertical des CV peu remplis | [`phase-3.md`](./phase-3.md) |

## Critères d'acceptation

- Un CV de formateur développement conserve des preuves de construction d'application, de formation et de pratique IA.
- Konexio, l'expérience full-stack et l'expérience d'animateur sont disponibles pour ce type d'annonce sans qu'une IA puisse les supprimer silencieusement.
- Le projet personnel sélectionné par les règles est conservé pendant la rédaction et la correction.
- Un jugement final insuffisant déclenche une nouvelle correction puis reste visible comme « à corriger » s'il persiste.
- La page affiche le verdict et les problèmes des agents, et permet de régénérer le même CV.
- Un contenu principal court est recentré verticalement sans déplacer les CV denses.
- Les tests Python et la construction du frontend réussissent.
