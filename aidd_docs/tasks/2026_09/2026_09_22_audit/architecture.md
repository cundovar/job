# Codebase Audit: recherche d'agences de bout en bout

La chaine actuelle est sur-construite par rapport au besoin, tout en laissant trois ruptures de contrat visibles : donnees manuelles melangees aux decouvertes, perimetre non strict et front non rafraichi.

- **Date**: 2026-09-22
- **Scope**: `tools/agency_prospecting_v2.py`, `tools/agency_registry.py`, `tools/city_resolver.py`, `tools/official_site.py`, `agency_analysis/fit_analyzer.py`, `server/services/agenciesService.js`, `server/routes/applications.js`, `front/src/App.jsx`, `config/companies.csv`
- **Health**: poor
- **Findings**: 3 critical, 3 warning, 0 minor

## Findings

| Sev | Category | Location | Issue | Suggested fix | Effort |
| --- | --- | --- | --- | --- | --- |
| 🔴 | architecture | `config/companies.csv:2` | Les cinq anciennes cibles contestees sont encore versionnees et `merge_curated_agencies` les reinjecte dans chaque nouvelle recherche, qu'elles aient ete decouvertes ou non. Le resultat affiche n'est donc pas le resultat de la recherche demandee. | Supprimer les cinq lignes et ne plus fusionner les cibles manuelles dans un snapshot de decouverte. Garder une liste d'exclusion ou une liste de favoris separee si necessaire. | S |
| 🔴 | architecture | `tools/agency_prospecting_v2.py:217` | Le preset `paris-20` couvre explicitement les 10e, 11e, 12e, 19e et des communes voisines. Il contredit la demande fonctionnelle `Paris 20 = adresse verifiee 75020`. | Remplacer ce preset par un perimetre administratif strict `postal_code == 75020`; ne jamais ajouter de rayon implicite. | S |
| 🔴 | architecture | `front/src/App.jsx:1286` | L'index des recherches n'est charge qu'au montage. Le front n'observe pas la tache de recherche et conserve prioritairement l'ancien `selectedId`; un nouveau snapshot peut donc exister sans devenir visible. | A la completion de `agency_status`, recharger l'index en `no-store`, selectionner le `search_id` retourne, puis charger ce snapshot. Ajouter aussi un bouton Actualiser comme repli. | M |
| 🟡 | architecture | `tools/agency_prospecting_v2.py:2140` | La source de decouverte repose sur le HTML instable de DuckDuckGo/Bing et des annuaires, alors que le besoin porte sur des etablissements locaux avec nom, adresse et site. Une grande cascade de verification compense une source initiale mal adaptee. | Introduire un collecteur local structure unique (Google Places Text Search si cle/budget acceptes, ou autre source locale structuree), puis normaliser seulement `name`, `website`, `formatted_address`, `postal_code` et `source`. Garder Bing/DDG uniquement en repli. | M |
| 🟡 | architecture | `tools/agency_prospecting_v2.py:2178` | La presélection lit seulement l'accueil et elimine avant le crawl des pages contact/mentions legales, qui portent souvent l'adresse et l'activite. La chaine perd des candidats avant d'avoir lu les preuves utiles. | Pour un resultat local deja adresse, supprimer cette presélection. Pour les autres, lire au minimum accueil + contact/mentions avant la decision. | M |
| 🟡 | architecture | `tools/agency_prospecting_v2.py:2397` | L'analyse profil existe deja, mais elle est conditionnee par le score du moteur. Une agence locale avec adresse et site valides peut ne jamais recevoir ses points forts/faibles parce qu'un barème intermediaire l'a ecartee. | Appliquer l'analyse a toute agence dedupliquee ayant `postal_code=75020` et un site officiel lisible; utiliser son verdict comme qualification finale plutot qu'un second filtre opaque. | S |

## Top actions

1. Corriger le contrat de donnees : retirer les cinq lignes manuelles, separer favoris/exclusions des resultats de recherche et imposer `75020` a la publication.
2. Remplacer la cascade de decouverte par le flux minimal `source locale structuree -> dedoublonnage domaine/place id -> crawl du site -> analyse profil -> publication`.
3. Relier la completion de la tache au front : `search_id` retourne -> index recharge -> nouvelle recherche selectionnee -> snapshot affiche.
4. Une fois ce flux valide, extraire les collecteurs de `agency_prospecting_v2.py`; ne pas refactorer les 2 620 lignes avant d'avoir verrouille le comportement simple attendu.

## Couverture

- **Scanne**: architecture, frontiere collecte/qualification, orchestration asynchrone, publication et consommation front
- **Ignore**: securite, dependances, performance detaillee, couverture exhaustive des tests et audit visuel; hors du perimetre demande

## Architecture cible minimale

```text
"agence web Paris 20"
        |
        v
source locale structuree
(nom + adresse + site)
        |
        v
adresse verifiee 75020
        |
        v
dedoublonnage domaine / identifiant source
        |
        v
crawl site officiel (accueil + services + contact)
        |
        v
analyse existante : activite + points forts/faibles + adequation profil
        |
        v
snapshot JSON -> search_id -> rafraichissement du front
```

Le registre d'entreprises, la recherche secondaire du site officiel, le geocodage par distance et les presets geographiques ne doivent intervenir qu'en repli, pas dans le chemin nominal de Paris 20.
