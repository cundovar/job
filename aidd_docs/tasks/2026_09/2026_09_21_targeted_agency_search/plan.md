---
objective: "La prospection d'agences devient une chaîne géographique, vérifiable et auditable allant de la découverte à l'envoi, avec une autonomie qui n'augmente qu'après validation humaine et mesure de sa fiabilité."
status: in-progress
---

# Plan: Prospection d'agences ciblée vers automatisation supervisée

## Overview

| Field      | Value |
| ---------- | ----- |
| **Goal**   | Rechercher, qualifier et traiter des agences partout en France, puis augmenter progressivement l'autonomie sous contrôle humain mesuré. |
| **Source** | `/home/cundo/.codex/attachments/f123fc3f-7b9a-4cc4-988c-4d21b272734e/pasted-text.txt` + `/home/cundo/.codex/attachments/87cb537e-0dab-4831-a9ce-afa0d339bbc5/pasted-text.txt` + `/home/cundo/.codex/attachments/d4a05038-d59a-42a1-8ecf-8380ae393f75/pasted-text.txt` |

## Phases

| #   | Phase | File |
| --- | ----- | ---- |
| 1 | Découverte hybride, adresses officielles et barème fiable | [`phase-1.md`](./phase-1.md) |
| 2 | Points forts, points faibles et angle de candidature | [`phase-2.md`](./phase-2.md) |
| 3 | Historique par recherche et sélecteur géographique | [`phase-3.md`](./phase-3.md) |
| 4 | Mode ville générique de bout en bout | [`phase-4.md`](./phase-4.md) |
| 4b | Découverte web-first et recherche du site officiel | [`phase-4b.md`](./phase-4b.md) |
| 5 | Mesure du juge d'agences et porte de fiabilité | [`phase-5.md`](./phase-5.md) |
| 6 | Préparation automatique avec validation humaine en lot | [`phase-6.md`](./phase-6.md) |
| 7 | Approbation conditionnelle par agent | [`phase-7.md`](./phase-7.md) |
| 8 | Envoi automatique sous quotas et coupe-circuit | [`phase-8.md`](./phase-8.md) |

## Resources

| Source | Verified |
| ------ | -------- |
| [API Recherche d'Entreprises](https://www.data.gouv.fr/dataservices/api-recherche-dentreprises) | API ouverte, recherche textuelle et géographique, filtres NAF et code postal, limite annoncée de 7 appels/s. |
| [Documentation Annuaire des Entreprises](https://annuaire-entreprises.data.gouv.fr/donnees/api-entreprises) | L'API agrège les principales données ouvertes Sirene/RNE et ne requiert pas le jeton réservé à API Entreprise. |
| [Dépôt officiel de l'API](https://github.com/annuaire-entreprises-data-gouv-fr/search-api) | Point d'entrée public et possibilités de recherche par nom, adresse et code NAF. |

## Decisions

| Decision | Why |
| -------- | --- |
| Utiliser l'API Recherche d'Entreprises, pas PagesJaunes ni l'API Entreprise authentifiée | Source publique, légale, sans clé, adaptée à la recherche et aux adresses ouvertes. |
| Traiter le registre comme source de candidats et d'adresses, jamais comme juge d'activité | Un code APE de développement peut appartenir à une ESN, un freelance ou une activité sans rapport avec une agence web. |
| Garder une découverte hybride web + registre | Le web révèle l'auto-description et le site réel ; le registre retrouve des structures locales invisibles des moteurs. |
| Rendre le web primaire et le registre secondaire, avec une étape explicite « trouver le site officiel » (phase 4b) | Constat d'usage : un candidat registre arrive sans site, donc en `incertain 0/100`, et ne devient jamais une piste. Masquer ces fiches supprime le bruit sans produire de signal ; seule une recherche de site prouvée rend le registre exploitable. |
| Conserver `agence` et `formation` comme deux catégories de premier rang | Les organismes RGAA/numérique comme Access42 ou Simplon sont des cibles légitimes avec un positionnement différent. |
| Conserver les preuves séparées selon leur origine | Une adresse légale issue de Sirene/RNE ne prouve pas que le site web appartient à l'entreprise ; chaque champ garde sa source. |
| Stocker une recherche sous un identifiant immuable et maintenir `latest.json` comme alias de compatibilité | Les recherches Montreuil, Paris et Lille coexistent sans casser les consommateurs actuels. |
| Résoudre une ville dynamiquement au lieu d'étendre `ZONES` | Le besoin couvre toute la France et ne doit pas introduire une entrée codée en dur par commune. |
| Exécuter l'analyse IA seulement après dédoublonnage et présélection, avec cache par empreinte | Le jugement reste utile sans multiplier inutilement les appels ni rallonger chaque relance identique. |
| Persister l'analyse par domaine et empreinte, puis en figer une copie dans chaque recherche | Une analyse survit aux runs tout en restant relisible dans le contexte exact qui l'a produite. |
| Garder Python pour la collecte et les agents pour le jugement | La découverte, les quotas et les garde-fous restent reproductibles sans dépendre d'une conversation Hermes. |
| Considérer tout texte web comme une donnée non fiable | Le contenu crawlable nourrit les preuves et le jugement, mais ne devient jamais une instruction pour l'agent. |
| Plafonner appels externes et coûts par run | Registre, géocodage, crawl et IA ont chacun une limite, un cache et des compteurs publiés. |
| Démarrer chaque phase uniquement sur un `go` explicite | Le plan peut être livré progressivement et chaque résultat reste vérifiable avant d'élargir le périmètre. |
| Exiger une gate mesurée en plus du `go` entre les phases 5 à 8 | Préparer, approuver et envoyer n'ont pas le même niveau de risque et ne doivent jamais être activés ensemble implicitement. |
| Mesurer les désaccords avant toute approbation automatique | Une impression de qualité ne suffit pas pour retirer une porte humaine. |
| Ne jamais rendre l'envoi automatique irréversible | File différée, quota, déduplication, liste d'exclusion, veto et coupe-circuit restent obligatoires. |
