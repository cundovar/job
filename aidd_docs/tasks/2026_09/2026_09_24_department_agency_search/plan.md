---
objective: "Permettre une prospection vérifiable par département partout en France, sans coder une liste de départements et sans dégrader le mode commune existant."
status: implemented
---

# Plan: Recherche d'agences par département

## Overview

| Field      | Value                   |
| ---------- | ----------------------- |
| **Goal**   | Rechercher agences et organismes de formation sur un département dynamique, avec preuves d'implantation et historique par recherche. |
| **Source** | Demande utilisateur du 24/09/2026, [conversation jointe](/home/cundo/.codex/attachments/331df960-266c-48b7-b3bf-2f30f53f6532/pasted-text.txt), code actuel et runbook de prospection. |

## Phases

| # | Phase | File |
| --- | --- | --- |
| 1 | Résolution dynamique et contrat de périmètre | [`phase-1.md`](./phase-1.md) |
| 2 | Découverte, registre et preuve départementale | [`phase-2.md`](./phase-2.md) |
| 3 | API asynchrone et interface de lancement | [`phase-3.md`](./phase-3.md) |
| 4 | Tests de non-régression et documentation | [`phase-4.md`](./phase-4.md) |

## Resources

| Source | Verified |
| ------ | -------- |
| [API Découpage administratif](https://geo.api.gouv.fr/decoupage-administratif.html) | L'API publique expose départements et communes, sans clé ; elle permet de résoudre dynamiquement le code, le nom et les communes d'un département. |
| [API Recherche d'Entreprises](https://www.data.gouv.fr/dataservices/api-recherche-dentreprises) | Le registre utilisé par le projet accepte un filtre département ; ses résultats restent des candidats/adresses, pas un verdict d'activité. |

## Decisions

| Decision | Why |
| -------- | --- |
| Trois périmètres exclusifs : `--zone`, `--ville` et `--departement` seul. | Une recherche ne doit jamais mélanger un préréglage, une commune et un département ni choisir un repli silencieux. |
| Résoudre le département à l'exécution auprès de geo.api.gouv.fr. | Les 101 départements, y compris 2A, 2B et outre-mer, restent supportés sans catalogue à maintenir. |
| Réutiliser `--departement` avec deux sens explicites. | Avec `--ville`, il lève l'homonymie ; seul, il définit le périmètre complet. |
| Le registre est interrogé directement avec son filtre département, pas commune par commune. | Évite des dizaines de passes, les throttlings et les doublons. |
| Une simple mention du code ou nom du département n'est jamais une preuve d'implantation. | Le défaut constaté dans le 93 ne doit pas être converti en résultat publiable. |
| Une adresse web est vérifiée contre une commune effectivement rattachée au département ; un siège registre doit déclarer ce département. | Un code postal seul peut couvrir plusieurs communes ou frontières ; la preuve doit rester géographique et traçable. |
| Limiter la découverte web au niveau départemental et borner explicitement les candidats à enrichir. | Le mode large doit rester prévisible en durée, coût et appels externes. |
