# TÂCHE : Bouton "J'ai postulé" — backend Node/Express + bouton frontend React

## Contexte du projet
Projet de recherche d'emploi. Le frontend React (Vite) est dans `front/` et tourne sur `localhost:5173`.
Il LIT uniquement des fichiers JSON statiques dans `front/public/data/`. Il n'a PAS de backend.
La liste des candidatures préparées est dans `front/public/data/candidatures.json` (clé `candidatures`, chaque item a un `id` slug, `entreprise`, `poste`, `date`, `lettre`, etc.).

Il existe DÉJÀ un tracker Python : `applications/application_tracker.py` (classe `ApplicationTracker`).
Il lit/écrit `data/applications_tracker.json` : un dict { key: record }. Chaque record "postulé" a au minimum :
  status="applied", applied_at (YYYY-MM-DD), follow_up_at (YYYY-MM-DD = applied_at + 7 jours),
  job_title, company, key, created_at, updated_at.
Un cron Python lit ce fichier pour lister les relances dues. NE PAS casser ce format.

## OBJECTIF (MVP, scope serré)
Permettre à l'utilisateur de cliquer un bouton "✅ J'ai postulé" sur chaque candidature dans le frontend.
Au clic : le statut passe à "applied", on enregistre applied_at = aujourd'hui et follow_up_at = +7 jours,
ce qui est PERSISTÉ sur disque (pas juste dans le navigateur). Le bouton reflète l'état (badge "Postulé le JJ/MM").

## ARCHITECTURE IMPOSÉE (évolution-ready — TRÈS IMPORTANT)
On commence en JSON mais le backend DOIT être prêt à passer à une vraie base de données plus tard SANS réécrire la logique métier. Donc :

Crée un dossier `server/` à la racine du projet avec :
```
server/
  package.json              (type: module, dépendances: express, cors)
  index.js                  (point d'entrée Express, port 3001)
  config.js                 (PORT=3001, chemins des fichiers data)
  routes/
    applications.js         (les endpoints REST)
  repositories/
    applicationsRepository.js      (CLASSE DE BASE / interface documentée — contrat: getAll(), getById(id), markApplied(id, data), markNotApplied(id))
    jsonApplicationsRepository.js   (implémentation JSON — la seule active aujourd'hui)
```
Le pattern Repository est le cœur du design : les routes ne connaissent QUE l'interface `applicationsRepository`.
Pour passer à une BDD plus tard, on créera `sqlApplicationsRepository.js` implémentant la même interface, et on changera UNE seule ligne dans `index.js`. Documente ça en commentaire en tête de `applicationsRepository.js`.

### Comportement de JsonApplicationsRepository
- Source de lecture des candidatures : `front/public/data/candidatures.json` (lecture seule, ne pas la modifier).
- Stockage des statuts "postulé" : ÉCRIRE dans `data/applications_tracker.json` au MÊME format que le tracker Python décrit ci-dessus (dict keyé par l'id de la candidature). Ainsi le cron relances Python fonctionnera directement.
- `getAll()` : retourne les candidatures fusionnées avec leur statut (applied ou non) lu depuis le tracker.
- `markApplied(id)` : calcule applied_at=aujourd'hui, follow_up_at=+7j, écrit le record dans le tracker JSON, retourne le record.
- `markNotApplied(id)` : retire le statut applied (supprime l'entrée ou repasse status à "ready_to_apply").
- Crée `data/` si absent. Gère le cas fichier inexistant / JSON vide proprement.

### Endpoints REST (routes/applications.js)
- `GET  /api/applications`            → liste des candidatures + statut
- `POST /api/applications/:id/applied`   → marque postulé, renvoie le record
- `POST /api/applications/:id/not-applied` → annule (au cas où clic par erreur)
- `GET  /api/health`                  → { ok: true } pour vérifier que le serveur tourne
Active CORS pour localhost:5173.

## FRONTEND (front/)
1. Configure le proxy Vite dans `front/vite.config.js` : les requêtes `/api` sont proxy vers `http://localhost:3001`.
2. Dans `front/src/App.jsx`, sur l'onglet/section Candidatures (📝), pour chaque candidature, ajoute :
   - Si NON postulé : un bouton "✅ J'ai postulé".
   - Si postulé : un badge vert "✅ Postulé le JJ/MM/AAAA · relance le JJ/MM" + petit lien "annuler".
   - Au clic, appelle l'API (`fetch('/api/applications/<id>/applied', {method:'POST'})`), puis met à jour l'UI.
3. Au chargement de la liste des candidatures, récupère les statuts via `GET /api/applications` (ou un endpoint de statuts) pour afficher l'état correct. Si le backend n'est pas joignable, dégrade proprement (le bouton reste cliquable mais affiche une erreur discrète, ne crash pas l'app).
4. Respecte le style existant (regarde App.css). Pas de nouvelle lib UI.

## DÉMARRAGE
- Ajoute dans `server/package.json` un script `"start": "node index.js"` et `"dev": "node --watch index.js"`.
- Mets à jour le README ou crée `server/README.md` expliquant : `cd server && npm install && npm start` (port 3001), puis `cd front && npm run dev` (port 5173).

## CONTRAINTES
- Node ESM (import/export), pas de TypeScript.
- Dépendances minimales : express + cors uniquement côté serveur. Pas de framework lourd.
- Code commenté en français, clair, lisible (l'utilisateur apprend).
- NE casse PAS le format de `data/applications_tracker.json` (compatibilité cron Python).
- NE modifie PAS les scripts Python existants.

## VÉRIFICATION (à faire toi-même avant de terminer)
1. `cd server && npm install` réussit.
2. Démarre le serveur (`node index.js`) en arrière-plan, teste avec curl :
   - `curl localhost:3001/api/health` → {ok:true}
   - `curl localhost:3001/api/applications` → liste avec la candidature Vitry
   - `curl -X POST localhost:3001/api/applications/2026-06-17_mon-assistant-numerique_consultant-formateur-vitry/applied` → record avec follow_up_at = applied_at +7j
   - Vérifie que `data/applications_tracker.json` contient bien l'entrée au bon format.
   - Annule avec l'endpoint not-applied et vérifie.
3. Build du front : `cd front && npm run build` doit passer sans erreur.
4. Arrête le serveur de test à la fin.
Rapporte précisément ce qui a été créé, les fichiers, et le résultat des tests curl.
