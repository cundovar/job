# TÂCHE : Recherche d'emploi lancée depuis le chat Hermes + correctif de saisie mobile

## Contexte

Projet de recherche d'emploi. Front React/Vite dans `front/` (localhost:5173), backend Node/Express dans `server/` (localhost:3001, patron Repository existant à respecter). Pipeline Python à la racine.

Le panneau de chat Hermes (`front/src/HermesChat.jsx`, `HermesChat.css`) permet de discuter avec l'agent Hermes via le proxy `server/routes/hermes.js`. Il fonctionne, mais :

1. L'utilisateur veut pouvoir **écrire sa demande précise dans le chat** et que **la recherche d'emploi soit lancée par Hermes** (et non par le pipeline figé du bouton « Lancer une recherche »). Le résultat doit apparaître comme **une session de recherche dans la liste « Sessions » de l'app** (carte « Recherche N ») : au clic, le détail par catégories s'affiche comme pour les recherches existantes.
2. Le champ de saisie du chat est **inutilisable sur téléphone** : le texte tapé ne s'affiche pas.

## Ce qui existe déjà (à réutiliser, ne pas réinventer)

### Côté Hermes (vérifié sur l'installation, v0.16.0, plateforme `api_server` activée)

L'API du gateway Hermes expose **en plus** du chat question/réponse classique (`POST /api/sessions/{id}/chat`, plafonné à 180 s côté proxy — **c'est ce plafond qui fait échouer toute demande de recherche**), des routes de tâche longue :

- `POST {HERMES_API_URL}/v1/runs` — body `{"input": "<message>"}` → renvoie **immédiatement** `{"run_id": "run_...", "status": "..."}`. Le tour d'agent continue en arrière-plan, sans plafond de 180 s.
- `GET  {HERMES_API_URL}/v1/runs/{run_id}` → `{"status": "running"|"completed"|"failed"|"cancelled", "output": "<texte final de l'agent>", "error": "...", "last_event": "...", ...}`. C'est **la notification de fin** : `output` contient la réponse finale de l'agent (recommandations incluses).
- (Hors scope pour l'instant) `GET /v1/runs/{run_id}/events` — flux SSE d'avancement.

Auth : header `Authorization: Bearer $HERMES_API_KEY`, mêmes identifiants que le proxy existant. **Ne jamais exposer la clé au navigateur.**

### Côté export des résultats

`front_export.py::export_front_data(jobs, search_id=None)` écrit les fichiers attendus par le front (`front/public/data/<search_id>/<categorie>.json`) et met à jour `index.json` (liste `searches` avec `total`, `found_total`, `already_seen`, `postuler`, `peut_etre`, `categories`). **Il accepte un `search_id` explicite** — c'est le point d'accroche : on peut donc créer une session « Recherche N » dédiée au run lancé depuis le chat, sans écraser la recherche du jour.

Le front liste déjà ces sessions (`index.searches` dans `App.jsx`, section « Sessions ») et ouvre le détail par catégories au clic (`openSearch`). **Ne pas modifier cette mécanique.**

## OBJECTIF

### Volet 1 — Chat : lancer une recherche sur demande explicite

- Nouvelle route serveur `POST /api/hermes/search` :
  - body `{sessionId, message}` (le message est la demande précise écrite par l'utilisateur dans le chat) ;
  - appelle `POST {HERMES_API_URL}/v1/runs` avec `{"input": <message enrichi d'une consigne de lancement>}` ;
  - **rend la main immédiatement** : renvoie `{runId}` sans attendre la fin du run ;
  - la consigne envoyée à l'agent doit lui demander de lancer la recherche d'emploi (pipeline `job_today` / `run_job_search`) puis de conclure par un compte rendu court : nombre d'offres trouvées, combien à postuler, combien en « peut-être ».
- Nouvelle route serveur `GET /api/hermes/search/:runId` :
  - appelle `GET /v1/runs/{runId}` et renvoie `{status, output, error}` (mappé proprement) ;
  - **statuts normalisés** : `running` / `done` / `failed` (mapper `completed` → `done`).
- Le déclenchement est **explicitement demandé par l'utilisateur** : l'agent ne doit pas partir en recherche spontanément. La consigne système envoyée avec la demande doit le dire.
- **Ne pas toucher** aux routes `/api/hermes/chat`, `/messages/:sessionId`, `/session` : le chat court reste tel quel pour les échanges d'écriture.
- **Ne pas toucher** à `POST /api/search/run` ni au bouton « Lancer une recherche » : il reste en place, inchangé.
- Une seule recherche à la fois : si un run est déjà en cours côté app, refuser proprement (409 avec message clair) plutôt que d'en lancer un second.

### Volet 2 — Front : attente, notification de fin, ouverture de la carte

Dans `HermesChat.jsx` :

- Si le message de l'utilisateur est une demande de recherche (route `/api/hermes/search`), alors :
  1. afficher immédiatement dans le fil un accusé de réception (« C'est lancé, je te préviens quand c'est fini ») ;
  2. sonder `GET /api/hermes/search/:runId` tant que `status === "running"` (intervalle 5 s, avec un indicateur discret d'attente) ;
  3. quand `status === "done"` : afficher le compte rendu (`output`) dans le fil, suivi d'un message renvoyant vers la carte de la recherche — **le résultat détaillé ne reste pas dans le chat, il est dans la page dédiée** ;
  4. si `status === "failed"` : afficher l'erreur proprement, sans casser l'app.
- Après un run terminé, **rafraîchir la liste des sessions côté app** pour que la nouvelle carte « Recherche N » apparaisse (mécanisme de `loadIndex` / `useSearchRunner` dans `App.jsx` — le composant de chat a besoin d'un moyen de déclencher ce rafraîchissement, par exemple une prop de callback passée depuis `App.jsx`).
- Le fond du panneau (texte tapé, envoi) et la logique existante doivent continuer de fonctionner.

**Comment décider si un message est une demande de recherche** : choix simple et robuste — un bouton explicite dans le panneau (par exemple « 🔎 Rechercher » à côté de l'envoi) qui envoie le message via la route de recherche, plutôt qu'une détection de mots-clés. Si tu choisis une détection côté serveur, elle doit être **explicite et conservatrice** (préfixe clair type `/recherche` ou commande visible), jamais une heuristique large : une phrase ambiguë ne doit jamais lancer un scraping.

### Volet 3 — Écriture du résultat comme session de recherche dédiée

- Le run lancé depuis le chat doit produire une **session visible dans la liste « Sessions »** de l'app (carte « Recherche N »), ouvrable et détaillée comme les autres.
- Réutiliser l'existant : `front_export.py::export_front_data(jobs, search_id=...)` avec un identifiant explicite et stable pour le run. **Ne pas dupliquer la logique d'export, ne pas modifier le format des fichiers produits.**
- Le mécanisme exact (qui appelle l'export et avec quel identifiant) est à choisir et à justifier dans le rapport : soit l'agent appelle l'outil/command existant qui exporte déjà (`hermes_commands/job_today.py` ou équivalent — **à vérifier avant d'écrire du code**), soit on ajoute un paramètre d'identifiant à la commande existante. Ne pas casser `data/applications_tracker.json` ni le format de `index.json`.

### Volet 4 — Correctif de saisie mobile (bug utilisateur)

- Sur téléphone, taper dans le champ du chat n'affiche rien. Cause probable identifiée : `HermesChat.css` applique `font-size: var(--fs-sm)` (13px) au textarea. **Sous 16px, iOS (Safari et Chrome) refuse la saisie en place et ouvre sa propre zone de saisie** → impression qu'aucun texte n'apparaît.
- Correctif attendu : `font-size: 16px` minimum sur le textarea **en dessous de 768px** (garder la taille actuelle sur desktop). Vérifier qu'aucun autre style (hauteur, `overflow`, z-index, `position: fixed` + clavier virtuel) ne bloque la saisie mobile, et corriger le cas échéant.
- Améliorer aussi la robustesse du chargement d'historique : dans `HermesChat.jsx`, `historyLoadedRef.current = true` est posé **avant** que la requête soit terminée ; si elle échoue, l'historique n'est plus jamais rechargé. Rendre le chargement réessayable après échec.
- **Honnêteté obligatoire dans le rapport** : si tu ne peux pas reproduire sur un vrai téléphone iOS/Android, dis-le explicitement et indique ce que tu as vérifié (CSS, seuil 16px, cohérence du build) sans affirmer que c'est résolu sur mobile.

## CONTRAINTES

- Node ESM, pas de TypeScript, **pas de nouvelle dépendance npm**. Front : pas de lib UI.
- La clé `HERMES_API_KEY` ne doit **jamais** apparaître dans le front ni dans un fichier commité (uniquement `.env`, gitignoré).
- Ne pas casser l'existant : routes `applications` / `search` / `agencies`, styles, bouton « Lancer une recherche », format de `index.json` et `data/applications_tracker.json`.
- `data/` n'est jamais commité (données personnelles).
- Code et commentaires en français quand ils s'adressent à l'utilisateur, identifiants en anglais.
- Utiliser le `fetch` global de Node, comme dans `server/routes/hermes.js`.
- Avant d'écrire du code, **vérifier** : (a) le nom exact et la signature de la commande d'export existante, (b) le schéma réel de la réponse de `/v1/runs`, (c) l'existence de `hermes_commands/job_today.py`. Ne pas spéculer.

## VÉRIFICATION (à faire toi-même avant de terminer)

1. `node --check` sur chaque fichier serveur créé/modifié.
2. Redémarrer le serveur Express puis, avec des vrais appels :
   - `curl -s -X POST localhost:3001/api/hermes/search -H 'Content-Type: application/json' -d '{"message":"<demande de test>"}'` → un `runId`, **retour immédiat** (chronométrer et le rapporter) ;
   - `curl -s localhost:3001/api/hermes/search/<runId>` → `running` puis `done` avec un `output` non vide (peut prendre plusieurs minutes : sonder, ne pas bloquer).
3. Vérifier qu'après un run terminé, `front/public/data/index.json` contient bien une entrée de session pour ce run et que les fichiers `<search_id>/<categorie>.json` existent.
4. `cd front && npm run build` passe sans erreur.
5. Ne pas laisser de doublon de processus sur le port 3001 (si un serveur tournait déjà, le redémarrer à l'identique).

## RAPPORT FINAL (en français)

Fichiers créés/modifiés, choix d'architecture retenus (notamment comment un message déclenche la recherche et comment l'export est appelé), extraits **réels** des curls avec les temps mesurés, résultat du build, et ce qui n'a **pas** pu être vérifié (mobile réel en particulier).
