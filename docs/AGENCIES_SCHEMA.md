# Schéma des données d'agences

> Depuis la phase 3, la vérité d'une passe vit sous son identifiant immuable
> (`searches/<search_id>.json`) et `latest.json` n'en est plus que l'**alias de
> compatibilité**. Voir « Historique par recherche » plus bas, et le
> [runbook](./AGENCY_PROSPECTING_RUNBOOK.md) pour les commandes et la reprise.

## Pourquoi un seul producteur

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
| Consommateur (API) | `server/routes/applications.js` — `GET /api/agencies/searches`, `GET /api/agencies/searches/:searchId`, `GET /api/agencies/analyses`, `POST /api/agencies/target` |
| Consommateur (UI) | `front/src/App.jsx` — liste « Agences web », sélecteur de recherche |
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
  // Préréglage historique (clé de ZONES) OU périmètre construit à l'exécution
  // pour --ville : "ville-montreuil-93". ZONES n'est pas la liste des villes
  // supportées, voir le runbook § 3.
  "zone": "paris-20",
  "zone_label": "Paris 20e / Nation",
  // Présent seulement en mode --ville. La commune vient de l'API Découpage
  // administratif : rien n'y est déduit d'un nom.
  "city": {
    "name": "Montreuil", "slug": "montreuil", "insee": "93048",
    "departement": "93", "departement_name": "Seine-Saint-Denis",
    "postal_codes": ["93100"], "latitude": 48.86, "longitude": 2.44,
    "label": "Montreuil (93 · Seine-Saint-Denis)",
    "source": "geo.api.gouv.fr (API Découpage administratif)"
  },
  // Combien d'agences sont réellement reliées à la commune, et par quoi.
  // null hors mode ville.
  "perimeter": {
    "city": "Montreuil", "insee": "93048",
    "verifie": 6,          // city_match = adresse ou registre
    "mention_seule": 4,    // le nom de la ville n'apparaît que dans une page
    "sans_lien": 2,
    "sans_lien_details": ["exemple.fr — aucune adresse lue"]
  },
  // Les deux familles de requêtes, conservées jusqu'au résultat : la piste
  // formateur ne doit pas se perdre entre la génération et l'affichage.
  "query_families": { "agence": ["agence web Montreuil", "..."],
                      "formation": ["formation numérique Montreuil", "..."] },
  // Étapes mesurées, dans l'ordre d'exécution. duration_ms null = en cours.
  "steps": [{ "name": "resolution", "duration_ms": 412, "volumes": {} },
            { "name": "decouverte_web", "duration_ms": 61230, "volumes": { "hotes": 75 } }],
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
| `city` | string \| null | Commune du périmètre demandé. Absent hors mode `--ville` |
| `city_match` | `adresse` \| `registre` \| `mention` \| `aucun` | Ce qui relie l'agence à cette commune |
| `city_match_evidence` | string | La preuve citée : code postal lu, code commune du registre, ou extrait de page |
| `site_match` | `siret affiché` \| `siren affiché` \| `adresse concordante` \| `raison sociale` \| `sources convergentes` \| `aucun` | Ce qui rattache le site à cette structure |
| `site_match_evidence` | string | La preuve citée : le SIREN lu et sur quelle page, l'adresse concordante, le domaine |
| `site_candidates` | object[] | Domaines examinés et **refusés**, avec leur motif. Un refus nommé, pas un vide |
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

## `city_match` : la même garantie appliquée à la commune

`how` dit d'où vient une position ; `city_match` dit ce qui relie l'agence à la
commune demandée. Les deux répondent à la même tentation : conclure d'un nom.

| `city_match` | Établi par | Dans le périmètre ? |
| --- | --- | --- |
| `adresse` | un code postal de la commune, lu dans une adresse (`how` valant `adresse` ou `contact/legales`) | oui |
| `registre` | le `code_commune` du siège déclaré, égal au code INSEE | oui |
| `mention` | le nom de la commune apparaît dans une page du site | **non** |
| `aucun` | rien | non |

Le filtre porte donc sur **l'adresse vérifiée et le code commune**, jamais sur un
nom lu dans une page : « nous intervenons à Lille » ne fait pas une implantation
lilloise. Les `mention` ne sont pas supprimés — ils sont classés en dernier et
disent pourquoi, parce qu'un résultat effacé se redécouvre au run suivant.

## `site_match` : la même garantie appliquée au site

Troisième membre de la famille. `how` dit d'où vient une position, `city_match`
ce qui relie l'agence à la commune, `site_match` **ce qui rattache un site à une
structure du registre**. Les trois répondent à la même tentation : conclure d'un
nom.

| `site_match` | Établi par | Force |
| --- | --- | --- |
| `siret affiché` | les 14 chiffres lus sur le site (séparateurs décoratifs recollés) | 5 |
| `siren affiché` | les 9 chiffres, avec bornes non chiffrées — sinon un numéro de commande suffirait | 4 |
| `adresse concordante` | code postal **et** nom de voie du siège, dans la même page | 3 |
| `raison sociale` | le nom **porte** le domaine (égalité) ou figure dans le titre | 2 |
| `sources convergentes` | plusieurs **moteurs** désignent le même domaine | 1 |
| `aucun` | rien — le site n'est pas retenu | 0 |

Le registre ne publie pas de site. Sans site, pas d'auto-description, donc pas
de verdict d'activité : le candidat restait `incertain`, `score: 0`, et
l'annuaire ne produisait que du bruit. L'étape manquante est
`registre → recherche du site officiel → vérification d'identité → crawl → score`.

**Sans preuve, on ignore.** `KONEXIO` ne devient pas `konexio.fr` parce que ça
tombe bien, et `konexio` n'est pas `konexio-formation.fr` : la comparaison au
domaine est une égalité, pas une inclusion. Les domaines examinés et refusés
restent dans `site_candidates` avec leur motif — un refus nommé, jamais un vide.

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

Quand `inside` vaut 0, la passe est publiée quand même — `latest.json` compris —
et le v2 le signale sur `stderr`. Ne pas écraser serait rassurant et faux :
l'écran continuerait d'afficher une prospection périmée en la faisant passer pour
l'actuelle.

## Produire le fichier

```bash
python3 tools/agency_prospecting_v2.py --zone paris-20 --radius 2000
python3 tools/agency_prospecting_v2.py --zone paris-20 --no-registry  # crawl web seul
```

Le registre n'est interrogé que sur les zones portant des **codes postaux
explicites**. Une zone comme `ile-de-france` n'en porte pas : deviner ses
communes reviendrait à choisir le périmètre de la recherche à la place de
l'utilisateur. Le cas remonte dans `registry.warnings`, jamais en silence.

## Historique par recherche (phase 3)

Une passe s'écrit sous un identifiant immuable, `search_id`, produit par
`make_search_id(zone_key, ts)` : `<zone-slug>-<AAAAMMJJ-HHMMSS>`. Le payload le
porte lui aussi, pour qu'un fichier lu isolément sache de quelle passe il vient.

```
front/public/data/agencies/
├── index.json                       # index des recherches publiées
├── latest.json                      # alias de compatibilité (dernière passe publiée)
└── searches/
    ├── montreuil-20260922-010000.json
    └── lille-20260922-020000.json
```

### `index.json`

```json
{
  "version": 1,
  "updated_at": "2026-09-22T02:00:00",
  "latest_search_id": "lille-20260922-020000",
  "searches": [
    {
      "search_id": "lille-20260922-020000",
      "zone": "lille", "zone_label": "Lille",
      "generated_at": "2026-09-22T02:00:00",
      "radius_m": 2000, "origin": "21 Rue Monte-Cristo, 75020 Paris",
      "total": 12, "address_known": 7,
      "categories": { "agence": 9, "formation": 3 },
      "analyses": { "analyzed": 4, "cache_hits": 8, "review": 1 },
      "state": "ok", "pinned": false,
      "file": "searches/lille-20260922-020000.json"
    }
  ]
}
```

- `address_known` ne compte que les positions issues d'une adresse **lue**
  (`how` ∈ `adresse`, `contact/legales`). Un centre d'arrondissement n'est pas
  une adresse, et l'index n'est pas l'endroit où cette règle se perd.
- `state` vaut `ok` ou `vide`. Une passe sans résultat est **quand même**
  enregistrée : son absence se relirait comme « pas de run ».
- `pinned` est une décision humaine, posée à la main dans le fichier. La
  rétention ne la contredit jamais.

### Règles de publication

`publish_search()` applique trois garanties :

1. `searches/<search_id>.json` est écrit **toujours** (atomiquement, `tmp` +
   `os.replace`), même si la passe n'a rien retenu ;
2. `latest.json` recopie la **dernière passe publiée, même vide**, et
   `latest_search_id` la suit. La règle inverse a été appliquée jusqu'au
   2026-09-22 : elle protégeait l'historique, mais elle rendait invisible toute
   correction qui *retire* des résultats. Une passe qui ne retient plus rien
   parce qu'on vient de filtrer des faux positifs doit vider l'écran, pas laisser
   le bruit d'avant s'y faire passer pour un résultat frais. La passe précédente
   n'est pas perdue pour autant : elle reste sous son `search_id` dans
   `searches/`, listée dans l'index ;
3. la rétention (20 recherches) ne supprime jamais une recherche `pinned`, celle
   que `latest.json` recopie, ni celle qui vient d'être publiée. Les
   identifiants supprimés sont listés dans `search.pruned` du récapitulatif.

### Le verdict IA voyage avec la recherche

Chaque agence du snapshot porte son bloc `analysis` (phase 2). Le snapshot est
donc relisible tel quel, sans dépendre du cache runtime
`data/agency_analyses.json` — lequel sert, lui, à survivre aux runs et à combler
une recherche antérieure à la phase 2. Le front affiche l'origine du jugement
(`recherche` ou `analyse persistée`) et son état (`obsolète`) sans jamais
requalifier l'un en l'autre.

### Ciblage

`POST /api/agencies/target` prend un `search_id` et relit l'agence dans **ce**
fichier. Sans `search_id` (ou avec `latest`), il retombe sur l'alias de
compatibilité. Un identifiant inconnu est refusé par un `404` qui **nomme les
recherches disponibles** : une liste vide se relirait comme « il n'y a rien ».
