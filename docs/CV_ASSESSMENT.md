# Évaluation des CV et version ATS

Le projet ne prétend pas reproduire la note interne d'un logiciel de recrutement. Chaque entreprise configure son ATS différemment. Le résultat produit ici est un indicateur interne, explicable et reproductible.

## Les cinq dimensions

| Dimension | Résultat | Signification |
|---|---|---|
| Éligibilité | `pass`, `fail`, `review` | Vérifie les critères explicitement éliminatoires présents dans l'annonce. Une information absente reste à vérifier. |
| Parsing | `pass`, `fail` | Relit le PDF ATS et vérifie que les champs essentiels sont extractibles. |
| Correspondance | 0–100 | Mesure les compétences, expériences, contexte métier, formations et contraintes prouvés par le profil maître. |
| Qualité humaine | 0–100 | Mesure pertinence, clarté, preuves, concision et aptitude à la mise en page. |
| Véracité | `pass`, `fail` | Bloque les expériences, compétences et affirmations absentes de la source de vérité. |

Le statut global est `ready`, `review` ou `blocked`. Un contrôle en échec bloque la validation. Une donnée inconnue produit `review`, jamais un faux échec.

## Pondérations initiales

La correspondance utilise la configuration versionnée `config/cv_assessment.json` :

- compétences obligatoires : 35 % ;
- expériences prouvées : 30 % ;
- métier et contexte : 15 % ;
- formation et certifications : 10 % ;
- contraintes : 10 %.

Les seuils `strong`, `credible`, `weak` et `poor` sont des catégories internes. Ils ne correspondent pas à une note visible dans Workday, Greenhouse, Oracle ou un autre ATS.

## Fichiers produits

- `cv_ats.pdf` et `cv_ats.html` : version mono-colonne, sans photo ni mise en page complexe ;
- `cv_final.pdf` et `cv_final.html` : version design destinée à la lecture humaine ;
- `cv_final.json` : contenu structuré du CV ;
- `cv_assessment.json` : évaluation détaillée ;
- fichiers JSON intermédiaires : traçabilité des agents et contrôles.

Les nouvelles générations ne produisent plus de fichiers Markdown ni de fichier de copie Canva.

## Défauts corrigés le 18/09/2026

Relevés sur les quatre dossiers de candidature spontanée du même jour. Les deux sont corrigés, avec tests, et les quatre `cv_assessment.json` ont été ré-évalués sans relancer l'IA.

### La Véracité rejetait les expériences groupées

**Symptôme.** Tous les CV produits échouaient en Véracité avec `unknown_experience: technical_missions_2026`.

**Cause.** Le profil maître déclare ses expériences dans **deux** listes : `experience_catalog` (les missions unitaires) et `experience_groups` (les regroupements, ici `display_mode: grouped_missions`). `technical_missions_2026` vit dans la seconde, et regroupe quatre missions toutes présentes dans la première. L'analyseur (`ai_agents.py:685`) et le créateur (`cv_creator.py:98`, `:122`) produisaient donc légitimement un bloc groupé portant l'identifiant du groupe, mais `evaluate_truthfulness` ne connaissait que `experience_catalog` : deux briques lisaient le même profil maître avec deux définitions différentes de « expérience connue ».

**Correctif.** `evaluate_truthfulness` (`cv_assessment.py`) accepte désormais un bloc groupé sous **trois conditions cumulatives** : le groupe est déclaré dans `experience_groups`, les membres utilisés (`source_experience_ids`, sinon `member_ids`) sont des membres déclarés du groupe, et chaque membre déclaré existe dans le catalogue unitaire. Un groupe mal déclaré ou un bloc qui s'appuie sur des missions non prévues échoue toujours. Ce n'est pas un affaiblissement du garde-fou : le groupe et ses membres restent intégralement reliés à la source de vérité. Les deux voies (annonce et spontanée) passent par la même `prepare_custom_cv`, le correctif couvre donc les deux.

### La revue IA pouvait masquer un `blocked`

**Symptôme.** Sur les quatre dossiers, trois étaient en `review` alors que la Véracité était en échec — un seul conservait son `blocked`.

**Cause.** `_apply_final_review_status` (`pipeline.py`) écrasait `overall_status` en `review` dès que la revue IA répondait `needs_revision`, y compris quand un contrôle Python avait bloqué le CV. L'opinion de la réviseuse survotait le garde-fou, en contradiction avec l'invariant « un contrôle en échec bloque la validation ».

**Correctif.** La revue IA ne déclasse plus que les statuts `ready` : elle peut retarder un CV prêt, jamais débloquer un contrôle en échec.

### Ce que le correctif a changé sur les quatre dossiers

Ré-évaluation du 18/09/2026, à partir des fichiers déjà produits (offre, plan, `cv_final.json`, PDF ATS, revue finale) — sans relancer l'IA, seul le jugement était faux, pas le contenu.

| Dossier | Avant | Après |
|---|---|---|
| agence-jaam | `review` (échec Véracité masqué) | `review` — revue IA `needs_revision` |
| agence-limite | `review` (échec Véracité masqué) | `review` — revue IA `needs_revision` |
| econovia | `review` (échec Véracité masqué) | `review` — revue IA `needs_revision` |
| l-agence-rup | `blocked` | `ready` — match 78, revue `needs_minor_revision` |

Plus aucun `unknown_experience` : le faux échec a disparu, et un dossier en réalité prêt réapparaît. Les trois autres restent en `review` pour une raison légitime cette fois — la revue IA demande une révision, ce qui retarde sans bloquer.

### Couverture de test

Sept tests ajoutés à `tests/test_cv_generator.py`, sur des profils maîtres synthétiques (jamais une copie du profil réel, règle 1 du `CLAUDE.md`) :

- groupe déclaré accepté, avec et sans `source_experience_ids` ;
- groupe non déclaré rejeté ;
- groupe dont un membre est absent du catalogue rejeté ;
- bloc s'appuyant sur des membres non prévus rejeté ;
- la revue IA ne dégrade pas un `blocked` ;
- la revue IA dégrade un `ready` en `review`.

## Limites

Les questions posées dans le formulaire de candidature peuvent déclencher un rejet externe et ne figurent pas toujours dans l'annonce. Le système ne peut donc pas garantir le passage d'un ATS. Il ne doit pas déduire qu'un refus provient automatiquement du CV ou de l'ATS.

La calibration future doit utiliser des résultats observables : candidature envoyée, réponse humaine, entretien obtenu et motif de refus connu. Les pondérations ne doivent être ajustées qu'après plusieurs cas comparables.

## Compatibilité

Les anciens dossiers contenant uniquement `quality_score` et `ats_score` restent lisibles dans l'interface. Ces champs sont temporairement dérivés des nouvelles dimensions pour les nouvelles générations et pourront être retirés après migration des dossiers utiles.
