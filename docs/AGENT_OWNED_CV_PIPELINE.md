# La chaîne CV : qui décide, qui vérifie, qui autorise l'export

Ce document fixe la frontière entre ce que les agents IA décident et ce que
Python contrôle. Il existe parce que la frontière avait glissé : des règles
déterministes réinjectaient des expériences écartées, tronquaient des puces et
ne conservaient que la première preuve de chaque mission groupée — le CV CARECO
perdait ainsi WooCommerce, API REST, Twig, Bootstrap et Git après composition.

## La règle en une phrase

**Les agents décident du contenu éditorial. Python vérifie la vérité, le format
et le droit d'exporter — sans jamais réécrire un choix d'agent.**

Concrètement, Python ne doit jamais : ajouter une expérience, un projet, une
compétence ou une formation ; réordonner une liste ; tronquer un texte ;
supprimer une formulation ; fabriquer une puce de remplacement. Quand quelque
chose ne va pas, il produit une **erreur localisée** que le réviseur traite.

## Les cinq agents

| Agent | Rôle configuré | Entrées | Sortie | Droits |
|---|---|---|---|---|
| Analyste | `cv_job_analyzer` | annonce, consignes candidat, source de vérité, préanalyse Python | plan d'adaptation | Choisit la variante, les expériences, l'ordre des sections, les projets, le regroupement. Aucun identifiant n'est imposé. |
| Rédacteur | `cv_creator` | annonce, consignes, source de vérité, plan, squelette structurel | contenu du CV | Écrit titre, accroche, compétences, puces sourcées, blocs groupés, projets, formations. Sélectionne et omet librement. |
| Vérificateur de vérité | `cv_truth_checker` | source de vérité, CV, contrôle Python | verdict `accepted`/`refused` + constats par puce | **Accepte ou refuse uniquement.** Ne juge ni la pertinence, ni le style. Ne propose aucune reformulation. |
| Juge recruteur | `cv_quality_checker` | annonce, consignes, source de vérité, plan, CV, contrôle Python | verdict, scores, problèmes, couverture des preuves | Seul maître de la pertinence, de la lisibilité, de la couverture et de l'ATS. |
| Réviseur | `cv_style_reviser` | annonce, consignes, source de vérité, plan, brouillon, jugement, **contrat de correction** | contenu du CV corrigé | Ajoute, retire et réordonne librement tout élément sourcé. |

Le routage provider/modèle de chaque rôle vit dans `config/ai_role_routing.json`.

Le vérificateur de vérité ne reçoit **ni l'annonce ni les consignes candidat** :
il ne doit pas pouvoir être influencé par ce que le poste attend.

## Ce que Python valide

`cv_generator/cv_truth_validator.py` est une fonction pure. Elle reçoit un CV,
renvoie le **même objet** accompagné d'une liste d'erreurs. Elle ne mute rien.

### Le contrat de provenance

Chaque puce cite ses preuves dans `sources` :

```json
{"text": "Catalogue WooCommerce et API REST sur une boutique.",
 "sources": ["boutique_fictive:0", "boutique_fictive:1"]}
```

- `experience_id:index` désigne le highlight n° *index* de cette expérience ;
- `project_id` désigne un projet du catalogue ;
- une puce sans source est refusée ;
- une puce d'un **bloc groupé** ne peut citer que les missions de son groupe.

Un bloc groupé est écrit directement par l'agent :

```json
{"id": "missions_techniques_2026",
 "source_experience_ids": ["boutique_fictive", "atelier_imaginaire"],
 "bullets": [ ... une puce par preuve à conserver ... ]}
```

Le champ historique `source_highlight_indexes` reste lu pendant la migration :
il désigne implicitement les highlights de l'expérience qui porte la puce.

### Les trois familles d'erreurs

| Famille | Effet | Exemples de codes |
|---|---|---|
| `truth` | **Bloque la publication.** Statut `blocked`. | `UNKNOWN_EXPERIENCE`, `BULLET_WITHOUT_SOURCE`, `SOURCE_OUT_OF_RANGE`, `SOURCE_OUTSIDE_EXPERIENCE`, `UNDECLARED_GROUP_MEMBER`, `GROUP_TOO_FEW_MEMBERS`, `UNKNOWN_SKILL`, `UNKNOWN_PROJECT_TECHNOLOGY`, `UNKNOWN_EDUCATION`, `FORBIDDEN_CLAIM`, `CLAIM_NOT_SUPPORTED_BY_SOURCE`, `TEMPORAL_CLAIM_NOT_IN_SOURCE` |
| `format` | **Interdit l'export final**, corrigeable par une révision. Statut `review`. | `BULLET_TOO_LONG`, `TOO_MANY_BULLETS`, `PROFILE_TOO_LONG`, `TOO_MANY_SKILLS`, `EMPTY_EXPERIENCE`, `EXPERIENCE_ORDER_NOT_ANTICHRONOLOGICAL` |
| `source` | **Le profil maître ne dit pas ce qu'il faudrait.** Statut `review`, **sans aucun tour de révision** : aucun agent ne peut le réparer. | `SOURCE_END_DATE_UNCONFIRMED`, `SOURCE_TEMPORAL_CLAIM_CONFLICT` |

L'ordre antéchronologique est **signalé**, jamais rétabli : c'est au réviseur de
le corriger, faute de quoi Python déciderait à la place de l'agent.

### Les dates : rien n'est déduit d'une absence

Une période se lit telle quelle. **Une fin absente ne veut pas dire « en
cours »** : seul `"ongoing": true` l'affirme. Sans lui, la période se rend
`« 2023 – (fin à confirmer) »`, se trie sur sa date de début, et produit un
`SOURCE_END_DATE_UNCONFIRMED` qui met le CV en `review`.

C'est le défaut qui avait sorti un CV où un freelance 2023-2024 s'affichait
`« 2023 – Aujourd'hui »` **au-dessus** des missions 2026 : la fin manquait dans
le profil, et deux règles opposées s'en accommodaient — le rendu y lisait un
présent, le tri y lisait `9999-12`.

Une puce qui affirme une activité en cours (`depuis`, `aujourd'hui`,
`actuellement`) sur une période fermée est fautive dans les deux sens : si la
preuve citée le dit aussi, c'est le profil qui se contredit
(`SOURCE_TEMPORAL_CLAIM_CONFLICT`) ; si elle ne le dit pas, l'agent a ajouté une
date (`TEMPORAL_CLAIM_NOT_IN_SOURCE`, bloquant).

### Ce que Python n'a pas le droit de faire

Le contrôle déterministe `cv_quality_checker.review_cv` produit aussi des
signalements de pertinence (mots-clés absents, `SKILL_WITHOUT_EVIDENCE`). Ils
sont **transmis au juge, jamais imposés** : Python n'impose une révision que sur
une erreur de vérité, une erreur de gabarit, ou un verdict IA qui se contredit
(un juge qui signale un problème grave et conclut « validated »).

## La boucle de correction

```
plan → rédaction → vérité (Python puis agent) → juge recruteur
                        ↓ refusé              ↓ needs_revision
                        └──────→ réviseur ────┘   (3 fois au maximum)
```

- Python valide **avant** l'appel IA : une référence introuvable n'a pas besoin
  d'un agent pour être refusée.
- Le réviseur reçoit un **contrat de correction unique** fusionnant les trois
  origines, vérité d'abord : `{origin, blocking, code, location, problem}`.
- Trois révisions au maximum, arrêt immédiat dès validation.
- Arrêt anticipé sur **absence de progrès** : si l'empreinte du couple
  contenu/problèmes ne change pas, une passe de plus ne produirait rien.
- `cv_agent_trace.json` porte `rounds[]`, `stopped_because`
  (`validated` · `no_progress` · `revision_limit_reached`) et `published`.

## Statuts et artefacts

| Statut | Signification | Fichiers finaux | Envoi |
|---|---|---|---|
| `preparing` | génération en cours (état de la tâche asynchrone) | — | non |
| `ready` | vérité acceptée, gabarit conforme, évaluation `ready` | oui | oui |
| `review` | le juge demande une correction, une contrainte de gabarit subsiste, ou la source est incomplète | **non** | non |
| `blocked` | une affirmation n'est pas reliée au profil maître | **non** | non |
| `absent` | aucun CV généré — **le CV reste optionnel**, rien n'est bloqué | — | oui |

### Fichiers produits

Toujours, quel que soit le verdict :
`cv_adaptation_plan.json`, `cv_draft.json`, `cv_review.json`,
`cv_truth_check.json`, `cv_final_review.json`, **`cv_content.json`**
(le contenu retenu), `cv_agent_trace.json`, `cv_assessment.json`.

Uniquement si `ready` :
`cv_final.json`, `cv_final.html`, `cv_final.pdf`, `cv_ats.html`, `cv_ats.pdf`.

Sinon : `cv_review_preview.html`, `cv_review_preview.pdf`,
`cv_review_preview_ats.html`, `cv_review_preview_ats.pdf`.

**Les artefacts `cv_final.*` d'un run précédent sont supprimés** quand une
régénération n'aboutit pas à `ready` : ils décriraient un contenu que le
pipeline vient de refuser, et resteraient téléchargeables. La liste des fichiers
retirés est tracée dans `cv_agent_trace.json` (`stale_artefacts_removed`).

## Le contrat de publication côté serveur

`server/services/cvPublication.js` porte la **définition unique** de « ce CV
est-il publiable ». L'API, le catalogue et le front la lisent tous — auparavant
trois prédicats divergents cohabitaient, et aucun ne lisait `overall_status`.

- `GET /applications/:id/cv/status` expose `status`, `reason`,
  `blocking_issues`, `format_issues`, `source_issues`, `revision_rounds` ;
- le téléchargement d'un fichier final répond **409** hors `ready` ;
- l'approbation d'envoi et « J'ai postulé » sont refusées si un CV existe mais
  n'est pas validé ; **sans CV généré, le flux est inchangé** ;
- un dossier antérieur à ce contrat, sans évaluation lisible, est lu en
  `review` — jamais en `ready`.

## Tests

| Fichier | Couvre |
|---|---|
| `tests/test_cv_truth_validator.py` | contrat de provenance, absence de mutation, vérité vs format |
| `tests/test_cv_generator.py` | agents décideurs, cas CARECO, boucle bornée, verrou d'export |
| `tests/test_cv_assessment.py` | dimensions d'évaluation, plafonnement des scores, couverture des groupes |
| `tests/test_cv_publication_contract.py` | règle Node exécutée depuis pytest, concordance avec ce que le pipeline écrit |

Toute la chaîne CV tourne **sans `data/`**, sur `tests/fixtures/careco_cv_case.json`.
Commande : `pytest tests/` depuis la racine du dépôt.

## Le mode patch du réviseur

Par défaut, `revise` demande au réviseur un **patch ciblé** au lieu d'une
réécriture complète :

```json
{"changes": [{"action": "modify", "path": "experiences[0].bullets[2]",
              "new": {"text": "…", "sources": ["boutique_fictive:0"]}}]}
```

- Python applique les changements aux seuls chemins demandés et repasse le
  résultat dans l'assemblage déterministe : tout ce que le patch ne touche pas
  reste identique au brouillon — aucune partie déjà validée ne peut régresser.
- Le périmètre autorisé est l'ensemble des `location` bloquantes du contrat de
  correction (vérité + gabarit). Une `location` sans index — `experiences` pour
  `TOO_MANY_EXPERIENCES`, `skills` pour `TOO_MANY_SKILL_SECTIONS` — porte sur la
  liste entière et ouvre donc chacun de ses éléments, sans quoi la seule
  correction possible (retirer l'élément de trop) serait refusée.
- Un patch dont **un seul** changement est illisible ou hors périmètre est
  refusé en bloc, jamais appliqué à moitié, et la cause localisée du refus part
  dans le contrat de l'appel de repli (`origin: "patch"`).
- Les index d'un patch désignent le brouillon **entrant**. Python applique donc
  les `modify` d'abord, à index stables, puis les `remove` du dernier au
  premier : une suppression ne peut pas décaler une correction sur la puce
  voisine. Ce décalage serait invisible au validateur, les deux puces
  appartenant à la même expérience.
- Après **deux échecs de patch consécutifs**, le pipeline abandonne le mode
  patch et revient à la réécriture complète (chemin historique). Une réponse
  au schéma complet est aussi tolérée à tout moment.
- La revalidation intégrale (vérité puis juge) court après chaque patch, comme
  après chaque réécriture : le patch ne court-circuite aucun contrôle.

## L'arrêt ciblé sur la vérité

En complément de l'empreinte contenu/problèmes : si **deux tours de révision
consécutifs** produisent exactement les mêmes codes bloquants aux mêmes
chemins, la boucle s'arrête sur `stopped_because = "truth_no_progress"`, même
si le contenu a changé. Chaque appel est désormais daté
(`agent_run.duration_seconds`) pour arbitrer coûts et latence sur données.
