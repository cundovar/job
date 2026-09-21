# Tâche : boucle de révision CV — réparation du crash, révision par patch ciblé, observabilité

## Contexte (incident réel du 21/09 en production)

- **Crash** : `prepare_custom_cv` est mort sur `CVAgentError: L'agent cv_style_reviser_ai n'a
  retourné aucune expérience` (ai_agents.py `_assemble_cv_content`). Cause racine : `revise()`
  envoie au réviseur le brouillon **emballé** (`{"agent": …, "cv": {…}}`, cf. la forme retournée
  par `_assemble_cv_content`) alors que le prompt exige le schéma **à plat** du rédacteur. Un
  modèle qui imite la forme de son entrée répond `{"cv": {...}}` → `proposed.get("experiences")`
  absent → exception non interceptée → **aucun artefact ni statut écrit**, front aveugle.
- **Timeout** : un run en cours (`brainlogic`) a été tué à 15 min par `CV_TASK_TIMEOUT_MS`
  (serveur Express) pendant le tour 3/3, sans laisser de diagnostic.
- **Économie** : le run réussi du jour a montré qu'un tour complet (3 appels IA) peut ne rien
  corriger (mêmes 2 blocants de vérité aux tours 1 et 2) et que les verdicts `needs_minor_revision`
  n'ouvrent plus de tour depuis que `REVISION_STATUSES = {"needs_revision"}` (déjà changé, test
  `test_minor_revision_request_does_not_open_a_round` au vert — ne pas régresser).

## Règles non négociables (rappel CLAUDE.md, s'appliquent à cette tâche)

1. `data/` n'est jamais commité ni recopié dans un test — tout tourne sur
   `tests/fixtures/careco_cv_case.json`.
2. Le profil maître reste la seule source de vérité ; Python n'ajoute, ne réordonne, ne tronque,
   ne reformule jamais un contenu éditorial.
3. Une donnée inconnue produit `review`, jamais un faux échec : **aucune voie ne doit se terminer
   sans artefacts ni statut**.
4. Aucune sortie externe ; **ne rien commiter, ne rien pousser** — laisser le working tree propre
   et les tests au vert.

## Tâche 1 — Réparer le crash du réviseur (indispensable)

1. **Brouillon à plat** : dans `revise()` (ai_agents.py), envoyer `"brouillon": draft["cv"]`
   (la forme attendue en sortie, puces sourcées incluses) et aligner le `REVISER_PROMPT`
   (« rends exactement le schéma de `brouillon` »). Ne rien changer au créateur.
2. **Interception** : dans `prepare_custom_cv` (pipeline.py), intercepter `CVAgentError` venue de
   `create` ou `revise` :
   - `revise` → terminer sur le **dernier contenu valide** (le brouillon ; les `truth_check` et
     `review` déjà calculés portent sur ce contenu et restent valides), statut terminal normal
     (`ready` si vérité acceptée et gabarit conforme, sinon `review`), `stopped_because =
     "agent_contract_violation"`, tous les artefacts écrits, ménage des `cv_final.*` périmés via
     la branche non-`ready` existante.
   - `create` → aucun contenu : écrire plan, trace et assessment avec cause explicite
     (« rédacteur : contrat violé »), statut `review`, pas de `cv_content.json`.
3. **Salvage JSON durci** : `_parse_json_response` ne doit pas restituer un préfixe tronqué —
   si l'objet récupéré par le regex `\{.*\}` manque de clés minimales évidentes (au minimum une
   liste `experiences`), lever l'erreur « JSON invalide/tronqué » au lieu de laisser filer un
   objet creux. Si le fournisseur expose `finish_reason="length"` avec contenu non vide, même
   message « budget de complétion épuisé » que le cas contenu vide.

## Tâche 2 — Révision par patch ciblé (le cœur de la demande)

Aujourd'hui `revise()` fait réécrire le CV entier : chaque tour risque de casser des parties déjà
validées. Remplacer ce contrat par un **patch ciblé appliqué mécaniquement par Python** :

1. **Schéma du patch** rendu par le réviseur :
   `{"changes": [{"action": "modify"|"remove", "path": "experiences[i].bullets[j]" | "skills[k].items[m]" | …, "new": {…}}]}`
2. **Applier Python** : applique les changements aux seuls chemins ciblés ; tout ce qui n'est pas
   visé reste **octet pour octet identique** au brouillon entrant. Python est un exécuteur
   mécanique, jamais un auteur : il ne crée aucun contenu, il pose celui de l'agent.
3. **Périmètre garanti** : un `path` hors du périmètre du contrat de correction (les chemins des
   erreurs de `build_correction_contract` + gabarit) est refusé avec erreur localisée rendue au
   réviseur ; après 2 échecs de patch consécutifs, repli sur la réécriture complète actuelle
   (chemin existant conservé).
4. **Revalidation intégrale** après application (`verify()` + `review()` comme aujourd'hui) : la
   vérité reste le juge de paix, le patch ne court-circuite aucun contrôle.
5. `sections` prises en charge pour le patch : `profile`, `skills`, `experiences` (et leurs
   bullets/`source_experience_ids`), `projects`, `education` — mêmes structures que
   `_assemble_cv_content`.

## Tâche 3 — Arrêt anticipé ciblé sur la vérité

Dans la boucle : si deux tours consécutifs produisent **exactement les mêmes codes** d'erreurs de
vérité bloquantes (`code + path`), arrêter sur `no_progress` même si le contenu a changé. Les
erreurs de gabarit et les signalements de pertinence ne comptent pas dans cette empreinte.

## Tâche 4 — Observabilité

Dans `cv_agent_trace.json`, renseigner `agent_run.duration_seconds` (et `provider`/`model` déjà
prévus) pour chaque appel, y compris les tours de révision. C'est la donnée qui manque pour
arbitrer coûts/latence.

## Tests (hors ligne, fixture CARECO uniquement)

- Réviseur simulé qui renvoie `{"cv": {...}}` → **aucune exception**, statut terminal défini,
  artefacts écrits, `stopped_because="agent_contract_violation"`.
- Réviseur simulé JSON tronqué → erreur « JSON invalide/tronqué » interceptée comme en 1.
- Patch valide → seuls les chemins ciblés changent (comparer le reste à l'identique), revalidation
  passée, publication normale.
- Patch hors périmètre → erreur au réviseur, puis repli réécriture complète au 2ᵉ échec.
- Deux tours mêmes codes de vérité → `no_progress`.
- Régression : tous les tests existants de `tests/test_cv_generator.py`,
  `tests/test_cv_truth_validator.py`, `tests/test_cv_assessment.py`,
  `tests/test_cv_publication_contract.py` restent au vert (48 tests dans test_cv_generator
  aujourd'hui, ne pas en perdre un seul).

## Critère de fin

`pytest tests/test_cv_generator.py tests/test_cv_truth_validator.py tests/test_cv_assessment.py
tests/test_cv_publication_contract.py` → 100 % vert, nouveaux comportements couverts, working tree
non commité, aucune modification hors `cv_generator/`, `tests/` et la doc
`docs/AGENT_OWNED_CV_PIPELINE.md` (à mettre à jour si le contrat du réviseur change).
