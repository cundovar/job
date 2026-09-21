# Schéma de `front/public/data/agencies/latest.json`

Ce fichier est la liste d'agences que le dashboard affiche. Il a longtemps eu
**deux formes incompatibles** : celle produite par `tools/agency_prospecting_v2.py`
(`ok` / `version` / `zone` / `zone_stats` / `agencies`) et celle écrite au démarrage
du serveur Node par `seedCuratedAgencies()` (`agencies` / `curated_for` /
`generated_at`). La seconde écrasait la première à chaque boot, et ne portait ni
`address`, ni `distance_m`, ni `zone` : le dashboard devenait aveugle à la
géographie, et l'adresse des agences ne survivait qu'en texte libre dans `reasons`.

`seedCuratedAgencies()` a été supprimé. **`agency_prospecting_v2.py` est désormais
le seul producteur de ce fichier.**

## Producteur et consommateurs

| Rôle | Où |
| --- | --- |
| Producteur | `tools/agency_prospecting_v2.py` |
| Consommateur (API) | `server/routes/applications.js` — `POST /api/agencies/target` |
| Consommateur (UI) | `front/src/App.jsx` — liste « Agences web » |
| Source manuelle | `config/companies.csv` — adresses relevées à la main |
| Source registre | `tools/agency_registry.py` — API Recherche d'Entreprises (Sirene/RNE) |

## Les trois sources et leurs rôles

Une fiche peut venir de trois endroits. Chacun sait une chose, et une seule :

| `origin` | Apporte | N'apporte **jamais** |
| --- | --- | --- |
| `csv` | Les corrections humaines : nom, site, adresse relevée, SIREN saisi | — |
| `registre` | L'immatriculation (SIREN/SIRET) et le siège déclaré | L'activité réelle, le site web |
| `web` | Le site, l'auto-description, la stack, les contacts | L'identité administrative |

Le registre est un **fournisseur de candidats et d'adresses légales**, pas un
oracle d'activité. Un code APE `62.01Z` couvre indifféremment une agence web,
une ESN, un freelance en régie ou une société qui ne fait plus de web. Le
verdict d'activité vient d'ailleurs : de ce que la structure écrit sur
elle-même, lu par `classify_self_description`, qui cite toujours son extrait.

## Enveloppe

```jsonc
{
  "ok": true,
  "version": "v2",
  "generated_at": "2026-09-21T13:09:00",
  "total": 7,
  "zone": "paris-20",              // clé de ZONES dans le v2
  "zone_label": "Paris 20e / Nation",
  "distance_origin": "21 Rue Monte-Cristo, 75020 Paris",  // null si --no-distance
  "radius": null,                  // voir plus bas, null si --radius absent
  "registry": {
    "candidates": 34,
    // Vide quand tout s'est bien passé. Sinon la raison, en clair : un
    // compteur à 0 sans explication se relit « il n'y a rien dans cette zone ».
    "warnings": ["registre indisponible (...) — le crawl web continue seul"]
  },
  "origin_stats": { "csv": 8, "registre": 34, "web": 21 },
  // Les cibles écartées à la qualification restent nommées avec leur motif :
  // une cible qui disparaît sans trace est redécouverte, réévaluée, et finit
  // parfois par repasser.
  "ecartes": [{ "name": "Webflow", "website": "https://webflow.com/", "motif": "..." }],
  "agencies": []
}
```

## Une agence

| Champ | Type | Sens |
| --- | --- | --- |
| `name` | string | Nom relevé, jamais reformulé. Le CSV prime s'il en porte un |
| `website` | string \| null | URL racine ; `null` si aucune URL n'a été trouvée |
| `address` | string \| null | Adresse **lue** (site ou relevé manuel). `null` = inconnue |
| `postal_code` | string \| null | Code postal, uniquement s'il vient de l'adresse |
| `address_source` | string \| null | D'où vient l'adresse (voir ci-dessous) |
| `how` | string | Forme courte de `address_source`, voir le tableau |
| `distance_m` | number \| null | Distance à `distance_origin`. `null` = non mesurable |
| `zone_match` | `tier1` \| `tier2` \| `none` | Correspondance aux termes de zone |
| `score` | number | Score de pertinence (0-100). **Classe, n'élimine pas** |
| `raw_score` | number | Score avant bornage à 0-100 |
| `family_scores` | object | Détail `stack` / `agence` / `formation`, chacun plafonné |
| `signals` | object | `positive`, `negative`, `exclusion` — le détail derrière le score |
| `stack` | string[] | Technologies détectées sur le site |
| `emails` | string[] | Emails publics relevés |
| `contact_urls` | string[] | Pages de contact / recrutement |
| `category` | `agence` \| `formation` \| `incertain` \| `ecarte` | Verdict d'activité |
| `category_reason` | string | Pourquoi ce verdict, en une phrase |
| `category_evidence` | string[] | Les extraits cités. Vide pour `incertain` |
| `siren` | string \| null | SIREN. `null` tant que le rapprochement n'est pas sûr |
| `siret` | string \| null | SIRET du siège, mêmes conditions |
| `legal_address` | string \| null | Siège **déclaré au registre**. Pas un lieu de travail |
| `legal_address_source` | string \| null | Toujours le registre quand `legal_address` existe |
| `identity_match` | string | Comment les sources ont été rapprochées, voir le tableau |
| `identity_candidates` | object[] | Rapprochements **non confirmés**, nommés au lieu d'être appliqués |
| `identity_conflicts` | string[] | Deux clés d'une même fiche pointant vers deux groupes |
| `origins` | string[] | Parmi `csv`, `registre`, `web` |
| `registry_note` | string | Pourquoi le registre l'a listée — « l'activité réelle n'est pas prouvée » |
| `reasons` | string[] | Justifications. **Ne doit plus contenir l'adresse** |

## `category` : le verdict vient de l'auto-description

Quatre valeurs, et une seule façon d'en obtenir une : lire ce que la structure
écrit sur elle-même.

| `category` | Signifie | Conséquence |
| --- | --- | --- |
| `agence` | Elle se décrit comme agence/studio web | Retenue |
| `formation` | Elle se décrit comme organisme de formation | Retenue |
| `incertain` | L'auto-description ne tranche pas, ou est illisible | Retenue si `score >= 50` |
| `ecarte` | Plateforme, annuaire, ou exclusion humaine dans le CSV | Sortie, mais **nommée** dans `ecartes` |

Deux règles qui en découlent, et qui sont testées :

- **un formateur n'est jamais écarté pour n'être pas une agence.** Le barème est
  calibré sur le vocabulaire des agences ; appliquer son seuil à un organisme de
  formation éliminerait une cible au motif qu'elle est l'autre cible ;
- **une donnée manquante produit `incertain`, jamais `ecarte`.** Un écarté
  disparaît de la liste, un incertain y reste visible et qualifiable.

## `analysis` : le jugement IA d'adéquation (phase 2)

Après dédoublonnage, écartement hors zone et barème, chaque agence/formation
dont le score atteint le seuil (`fit_analysis.seuil_min_score`, défaut 45)
peut porter un bloc `analysis` produit par un LLM routé
(`config/ai_role_routing.json` → rôle `agency_fit` : deepseek_job puis glm_cv).

| Champ | Sens |
|---|---|
| `fit_status` | `ok` (contrat respecté) ou `review` (sortie invalide/indisponible — jamais de texte inventé) |
| `strengths` / `weaknesses` | Max 6 points chacun ; chaque point doit s'appuyer sur une page fournie |
| `application_angle` | Angle de candidature spontanée, adapté à `category` (jamais full-stack forcé) |
| `fit_summary` | Résumé de ce que la structure fait, vu des pages crawlées |
| `fit_score` | 0-10, adéquation profil ↔ structure |
| `confidence` | `haute` / `moyenne` / `faible` |
| `evidence_urls` | Uniquement des URLs présentes dans les pages fournies au modèle |
| `issues` | Problèmes de contrat relevés par la validation Python |
| `fingerprint` / `prompt_version` / `analyzed_at` / `provider` / `model` | Traçabilité du jugement |

Règles de persistance :

- Le cache runtime est `data/agency_analyses.json` (hors Git, volume persistant
  en prod), indexé par **domaine normalisé + empreinte** (pages + profil +
  version du prompt). Un changement de contenu pousse l'ancienne analyse en
  `history` (max 2, marquée `obsolete`) sans jamais la détruire.
- Une agence absente d'un run conserve son analyse : on n'écrit que les
  domaines analysés dans le run.
- Compteurs publiés dans l'enveloppe : `fit_analysis` (`eligible`, `analyzed`,
  `cache_hits`, `review`, `calls`, `plafond_atteint`, `archive`,
  `limite_appels`, `seuil_min_score`). Plafond dur : 15 appels IA par run ;
  `--no-ai` désactive la passe.
- Archive horodatée lisible : `output/agencies/analyses-<timestamp>.md`.
- Niveau **recherche** : une analyse n'est pas un constat vérifié — le
  Vérificateur n'intervient qu'au « Retenir & préparer ».

## `identity_match` : la garantie anti-invention sur l'identité

Ce que `how` est à l'adresse, `identity_match` l'est à l'identité : il dit
*comment* les fiches ont été rapprochées, pour qu'un rapprochement faible ne se
relise jamais comme un fait.

| `identity_match` | Rapproché par | Le registre monte dans la fiche ? |
| --- | --- | --- |
| `siret` | Identifiant d'établissement | oui |
| `siren` | Identifiant d'entreprise | oui |
| `domaine` | Même hôte web | oui |
| `nom normalisé (incertain)` | Ressemblance de noms seule | **non** → `identity_candidates` |
| `""` (vide) | Aucun rapprochement, fiche isolée | — |

Deux « Studio Bleu » normalisés pareil peuvent être deux sociétés. Publier le
site de l'une sous le SIREN de l'autre, ou lui attribuer le siège de l'autre,
serait invisible et faux. La fiche reste unique, mais l'identité administrative
attend dans `identity_candidates` jusqu'à ce qu'un humain la confirme — en
écrivant le SIREN dans la colonne `siren` de `config/companies.csv`.

## `how` : la garantie anti-invention

`how` dit *comment* la position a été obtenue. C'est le champ qui empêche de
confondre une adresse lue avec une localisation devinée.

| `how` | Signifie | Vaut adresse ? |
| --- | --- | --- |
| `adresse` | lue sur une page crawlée du site | oui |
| `contact/legales` | lue sur `/contact` ou `/mentions-legales` | oui |
| `siège (registre)` | siège déclaré au registre, aucune adresse publiée | oui |
| `ville/arr (~centre)` | centre de l'arrondissement, aucune adresse lue | **non** |
| `""` (vide) | aucune position | non |

Ordre de priorité quand plusieurs sont disponibles : relevé manuel (CSV), puis
adresse publiée sur le site, puis siège du registre, puis approximation.

Règles qui en découlent, et qui sont testées :

- une agence sans `address` ne reçoit jamais de `postal_code` ;
- une position `ville/arr (~centre)` n'est **jamais** comptée « dans le rayon » ;
- une adresse absente du registre **reste absente**. Le registre masque les
  structures non diffusibles au lieu de les omettre : le nom devient un gabarit
  et l'adresse disparaît. La compléter à partir de la commune produirait une
  adresse fabriquée et parfaitement crédible.

## Cache de géocodage

`data/geocode_cache.json`, indexé par adresse normalisée (espaces réduits,
casse repliée). Deux passes sur les mêmes adresses produisent les mêmes
distances sans un seul appel au géocodeur.

**Seuls les succès sont mémorisés.** Mémoriser un échec économiserait un appel,
mais une coupure réseau d'une minute figerait pour toujours des adresses
parfaitement géocodables en « position inconnue ». Le fichier vit dans `data/`,
qui est gitignoré : le perdre ne coûte qu'un run plus lent.

## Bloc `radius` (présent seulement avec `--radius`)

```jsonc
"radius": {
  "radius_m": 2000,
  "origin_query": "21 Rue Monte-Cristo, 75020 Paris",
  "inside": 3,          // adresse lue ET sous le rayon → seules celles-ci sont dans `agencies`
  "approximate": 4,     // sous le rayon mais position ~centre : pas une adresse
  "outside": 16,
  "unknown": 12,
  "approximate_position": [{ "name": "...", "website": "...", "dist_m": 900, "how": "ville/arr (~centre)" }],
  "outside_radius":       [{ "name": "...", "website": "...", "dist_m": 5400, "how": "adresse" }],
  "unknown_position":     [{ "name": "...", "website": "..." }]
}
```

Les écartés restent **nommés**. « Rien dans le rayon » doit pouvoir se relire
comme « ces N-là étaient trop loin », jamais comme un vide inexpliqué.

Quand `inside` vaut 0, `latest.json` n'est pas écrasé (on ne détruit pas une
prospection précédente pour une passe vide) et le v2 le signale sur `stderr`.

## Produire le fichier

```bash
python3 tools/agency_prospecting_v2.py --zone paris-20 --radius 2000
python3 tools/agency_prospecting_v2.py --zone paris-20 --no-registry  # crawl web seul
```

Le registre n'est interrogé que sur les zones portant des **codes postaux
explicites**. Une zone comme `ile-de-france` n'en porte pas : deviner ses
communes reviendrait à choisir le périmètre de la recherche à la place de
l'utilisateur. Le cas remonte dans `registry.warnings`, jamais en silence.
