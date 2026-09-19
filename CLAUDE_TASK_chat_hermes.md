# TÂCHE : Panneau chat Hermes intégré au front React (MVP, scope serré)

## Contexte du projet
Projet de recherche d'emploi. Frontend React/Vite dans `front/` (localhost:5173), backend Node/Express dans `server/` (localhost:3001, pattern Repository existant à respecter).

Un **agent Hermes** tourne désormais sur cette machine et expose une API de chat sur `http://127.0.0.1:8642` (API Server du gateway Hermes). Les identifiants sont déjà dans le `.env` à la racine du projet :
- `HERMES_API_URL=http://127.0.0.1:8642`
- `HERMES_API_KEY=<clé secrète — NE JAMAIS l'exposer au navigateur, ne jamais la committer>`

L'utilisateur veut **discuter avec l'agent Hermes depuis le front**, sans quitter l'app.

## Endpoints Hermes disponibles (testés et fonctionnels)
- `POST {HERMES_API_URL}/api/sessions` — header `Authorization: Bearer <HERMES_API_KEY>`, body `{}` → `201` avec `{"session": {"id": "api_..."}}`
- `GET {HERMES_API_URL}/api/sessions/{id}/messages` → `200` avec `{"data": [{"role": "user"|"assistant", "content": "..."}]}`
- `POST {HERMES_API_URL}/api/sessions/{id}/chat` — body `{"message": "..."}` → `200` avec `{"session_id": "...", "message": {"role": "assistant", "content": "..."}}`. **Un tour d'agent peut prendre 30-120 s** (l'agent réfléchit et peut utiliser des outils).

## OBJECTIF (MVP)
Un bouton flottant "💬 Hermes" en bas à droite du front ouvre un panneau de chat : liste de messages, champ de saisie, envoi, réponse de l'agent. La conversation persiste entre les rechargements de page (session Hermes réutilisée).

## ARCHITECTURE IMPOSÉE

### Serveur (server/) — proxy, la clé reste côté serveur
1. Nouveau fichier `server/routes/hermes.js` (même style que `routes/applications.js`) :
   - `POST /api/hermes/session` → crée une session Hermes (POST /api/sessions), renvoie `{sessionId}`
   - `GET  /api/hermes/messages/:sessionId` → historique mappé en `[{role, content}]` (ignorer les roles non user/assistant)
   - `POST /api/hermes/chat` → body `{sessionId, message}` → si pas de sessionId, crée la session d'abord ; appelle le chat Hermes ; renvoie `{sessionId, content}` ; en cas d'échec renvoie un JSON d'erreur propre `{error: "..."}` avec le bon code HTTP (502 si Hermes injoignable, timeout très long)
2. Utiliser le **fetch global de Node** (pas d'axios, pas de nouvelle dépendance). Timeout de la requête chat côté Express : **180000 ms**.
3. Charger `HERMES_API_URL`/`HERMES_API_KEY` depuis `process.env` ; si le serveur ne charge pas déjà le `.env` à la racine, le charger (dotenv est acceptable si déjà présent dans les dépendances, sinon lire le fichier à la main — ne pas ajouter de dépendance).
4. Monter le router dans `server/index.js` (ou là où les routes existantes sont montées), préfixe cohérent avec l'existant.

### Front (front/)
1. Dans `App.jsx` : bouton flottant fixe en bas à droite `💬 Hermes` (au-dessus du contenu, `position: fixed`), qui ouvre/ferme un panneau chat (drawer d'environ 380px de large, hauteur ~70vh, coin bas droit).
2. Panneau de chat :
   - Liste de messages : utilisateur aligné à droite, assistant à gauche, `white-space: pre-wrap` pour les sauts de ligne, auto-scroll en bas.
   - Textarea + bouton envoyer ; **Entrée = envoyer**, **Shift+Entrée = nouvelle ligne** ; désactiver l'envoi pendant qu'une réponse est attendue ; indicateur "réflexion…" (l'agent peut mettre 1-2 min).
   - `sessionId` persisté dans `localStorage` (clé `hermes_chat_session`). À l'ouverture du panneau : si session existante → charger l'historique via `GET /api/hermes/messages/:id` ; sinon rien jusqu'au premier envoi (le premier envoi crée la session via `POST /api/hermes/session` ou laisse `POST /api/hermes/chat` sans sessionId la créer).
   - Bouton "🗑 Nouvelle conversation" : vide le panneau, supprime le localStorage, repart sur une session vierge.
   - Affichage d'erreur discret si le backend/Hermes ne répond pas (pas de crash de l'app).
3. Style dans `App.css` (ou un `HermesChat.css` importé) cohérent avec l'existant (mêmes couleurs/cartes). Pas de lib UI.
4. Composant séparé `front/src/HermesChat.jsx` recommandé (garder App.jsx lisible), monté une seule fois dans App.

### Explicitement HORS SCOPE (MVP)
- Pas de streaming SSE (endpoint `/chat/stream` documenté pour plus tard)
- Pas de rendu markdown complet (pre-wrap suffit)
- Pas d'historique multi-conversations (une seule session active)

## CONTRAINTES
- Node ESM, pas de TypeScript, pas de nouvelle dépendance npm.
- La clé `HERMES_API_KEY` ne doit JAMAIS apparaître dans le code du front ni dans un fichier commité (uniquement `.env`, déjà gitignoré).
- Code et commentaires en français.
- Ne casse rien de l'existant (routes applications/search/agences, styles).

## VÉRIFICATION (à faire toi-même avant de terminer)
1. `node --check` sur chaque fichier serveur modifié/créé.
2. Démarre (ou redémarre) le serveur Express, puis :
   - `curl -s -X POST localhost:3001/api/hermes/session` → un sessionId
   - `curl -s -X POST localhost:3001/api/hermes/chat -H 'Content-Type: application/json' -d '{"sessionId": "<id>", "message": "Ping de test, réponds en une phrase."}'` → une vraie réponse de l'agent (peut prendre 1 min)
3. `cd front && npm run build` passe sans erreur.
4. Arrête le serveur de test si tu l'as démarré toi-même (ne laisse pas de doublon sur le port 3001 ; si un serveur tournait déjà avant, redémarre-le à l'identique).

Rapporte en français : fichiers créés/modifiés, résultats des curls (avec extraits des vraies réponses), résultat du build.
