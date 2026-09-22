# TODO — Dédoublonnage qui vide le front

**Statut :** ouvert, non traité (à reprendre quand Cundo va mieux)
**Date du constat :** 2026-09-20
**Sévérité :** gênant, pas bloquant. Aucune donnée perdue.

## Symptôme

Après la recherche du 2026-09-20, le front n'affiche aucune offre nouvelle.

`front/public/data/index.json`, entrée du 2026-09-20 :

```
total: 0 | found: 104 | seen: 104 | POSTULER: 0 | PEUT-ÊTRE: 0
```

Les 6 onglets normaux sont à 0. Le seul onglet rempli est `deja_vues.json` (104 offres, plusieurs à 100/100).

## Cause

`front_export.py` → `_merge_daily_jobs()` : toute offre dont l'identité est présente
dans les 30 derniers jours (`load_seen_keys(current_day)`, `history_days=30`) est
forcée dans la catégorie `deja_vues` au lieu de son onglet naturel.

Un mois de scraping des mêmes sources avec les mêmes mots-clés ⇒ les mêmes annonces
reviennent ⇒ tout est « déjà vu » ⇒ journées vides. Comportement prévu, mais devenu
contre-productif.

Point aggravant : les offres `POSTULER` subissent le même sort. Les 28 POSTULER du
cache global (`data/jobs_cache.json`) ne sont pas visibles dans le front.

## Ce qui n'est PAS la cause (vérifié)

- L'export tourne bien : `front/public/data/index.json` et `data/jobs_cache.json` ont
  la même date de modif (2026-09-20 09:50).
- Aucune base de données ne manque : le projet est volontairement en JSON.
  Les 5 fichiers lus par le serveur Node existent et sont valides
  (`data/applications_tracker.json` 82 entrées, `data/jobs_cache.json` 613 offres,
  `front/public/data/index.json` 28 recherches, `data/agencies_cache.json` 38,
  `data/companies_cache.json` 6).
- Le pipeline a bien produit 104 offres analysées et scorées.

## Options de correction (à choisir)

1. **Réduire la fenêtre** `history_days` de 30 à 7 dans `front_export.py`
   (appel `load_seen_keys`). Simple. Revoir les mêmes offres plus souvent, mais
   plus de journées vides.
2. **Forcer les POSTULER visibles** même si déjà vues : dans `_merge_daily_jobs()`,
   ne pas router vers `deja_vues` quand `_recommendation(job) == "POSTULER"`.
   Plus malin : ne jamais perdre une offre à fort intérêt.
3. **Les deux ensemble.**

Recommandation : option 3, mais la décision revient à Cundo.

## Précautions avant de toucher au code

- `front_export.py` tourne en local ET en prod (Coolify, build git `cundovar/job`).
- Sauvegarder `front/public/data/2026-09-20/` et `index.json` avant modif.
- Ne pas casser le format de `data/applications_tracker.json` (règle 5 de `CLAUDE.md`).
- Vérifier après coup que les POSTULER remontent bien dans leur onglet naturel.
- Mise en prod = commit + push puis redeploy Coolify.

## Rappel du contexte utile

- `front/public/data/` = ce que lit le front. `data/jobs_cache.json` = cache pipeline.
- `front_export.py` est le pont entre les deux. Sans lui le front ne voit rien.
- Onglets : `webmaster_formateur`, `nouvelles_portes`, `frontend`, `backend`,
  `non_classees`, `deja_vues`.
