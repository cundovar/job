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
  "agencies": []
}
```

## Une agence

| Champ | Type | Sens |
| --- | --- | --- |
| `name` | string | Nom relevé, jamais reformulé |
| `website` | string \| null | URL racine ; `null` si aucune URL n'a été trouvée |
| `address` | string \| null | Adresse **lue** (site ou relevé manuel). `null` = inconnue |
| `postal_code` | string \| null | Code postal, uniquement s'il vient de l'adresse |
| `address_source` | string \| null | D'où vient l'adresse (voir ci-dessous) |
| `how` | string | Forme courte de `address_source`, voir le tableau |
| `distance_m` | number \| null | Distance à `distance_origin`. `null` = non mesurable |
| `zone_match` | `tier1` \| `tier2` \| `none` | Correspondance aux termes de zone |
| `score` | number | Score de pertinence du v2 (0-100) |
| `stack` | string[] | Technologies détectées sur le site |
| `emails` | string[] | Emails publics relevés |
| `contact_urls` | string[] | Pages de contact / recrutement |
| `category` | `agence` \| `formation` | Type de structure |
| `reasons` | string[] | Justifications. **Ne doit plus contenir l'adresse** |

## `how` : la garantie anti-invention

`how` dit *comment* la position a été obtenue. C'est le champ qui empêche de
confondre une adresse lue avec une localisation devinée.

| `how` | Signifie | Vaut adresse ? |
| --- | --- | --- |
| `adresse` | lue sur une page crawlée du site | oui |
| `contact/legales` | lue sur `/contact` ou `/mentions-legales` | oui |
| `ville/arr (~centre)` | centre de l'arrondissement, aucune adresse lue | **non** |
| `""` (vide) | aucune position | non |

Règles qui en découlent, et qui sont testées :

- une agence sans `address` ne reçoit jamais de `postal_code` ;
- une position `ville/arr (~centre)` n'est **jamais** comptée « dans le rayon ».

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
```
