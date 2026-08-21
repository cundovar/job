# TÂCHE : Nouvelle page "✅ Postulées" dans le menu latéral

## Contexte
Frontend React (Vite) dans `front/`. Le composant principal est `front/src/App.jsx` (déjà lu, structure connue).
Le backend Node/Express tourne sur localhost:3001 et expose :
- `GET /api/applications` → liste des candidatures avec leur statut. Chaque item : { id, status, applied_at, follow_up_at, job_title?, company?, ... }.
  Le statut vaut "applied" si l'utilisateur a cliqué "J'ai postulé", sinon "ready_to_apply" (ou pas d'entrée).
Les candidatures complètes (lettre, poste, entreprise, date) sont dans `front/public/data/candidatures.json` (clé `candidatures`).

Le menu latéral (`<aside className="sidebar">` dans App.jsx) a actuellement DEUX boutons de mode pilotés par l'état `activeMode` :
- `activeMode === 'recherche'`  → bouton "🔍 Recherches"
- `activeMode === 'candidatures'` → bouton "📝 Candidatures" (montre `<CandidaturesView />`)

## OBJECTIF
Ajouter un TROISIÈME mode `activeMode === 'postulees'` avec :
1. Un nouveau bouton dans le menu latéral, juste APRÈS le bouton "📝 Candidatures" :
   - Libellé : "✅ Postulées"
   - Sous-texte (search-stats) : le NOMBRE de candidatures postulées, ex "3 postulées" (compté dynamiquement depuis /api/applications, status==='applied'). Si 0 → "Aucune".
2. Une nouvelle vue `<PostuleesView />` affichée quand `activeMode === 'postulees'`, qui liste UNIQUEMENT les candidatures dont status === 'applied'.

## Comportement de PostuleesView
- Au montage : fetch `/api/applications`, garde celles avec status==='applied'. Pour chaque, retrouve les détails (entreprise, poste, lettre) en croisant l'`id` avec `candidatures.json`.
- Affiche chaque candidature postulée sous forme de carte (réutilise le style des cartes existantes, classe `job-card`) avec :
   - Entreprise — Poste
   - 📅 Date de candidature : "Postulé le JJ/MM/AAAA"
   - 🔔 Relance : "le JJ/MM/AAAA" + un indicateur visuel si la date de relance est DÉPASSÉE ou AUJOURD'HUI (badge orange/rouge "⏰ À relancer !") vs future (badge neutre "relance prévue").
   - Clic sur la carte → ouvre le détail de la lettre (réutilise la même logique que CandidaturesView : voir/copier la lettre). Tu peux factoriser ou dupliquer proprement.
   - Un bouton "annuler la postulation" (appelle POST /api/applications/:id/not-applied), qui retire la candidature de cette liste.
- Tri : par date de relance la plus proche en premier (les "à relancer" en haut).
- État vide : si aucune candidature postulée, message sympa "Aucune candidature postulée pour l'instant. Va dans 📝 Candidatures et clique '✅ J'ai postulé'."
- Dégradation propre si backend injoignable (même pattern que CandidaturesView : bandeau d'avertissement, pas de crash).
- Réutilise les helpers existants `fmtDate` et `fmtShort` (déjà définis en haut de App.jsx).

## Style
- Réutilise les classes CSS existantes au maximum (job-card, badge, sidebar, mode-btn, etc.).
- Pour le badge "À relancer" dépassé, ajoute une petite classe CSS (ex `.badge-relance-due` orange/rouge) dans App.css, cohérente avec le thème sombre existant.

## CONTRAINTES
- Modifie UNIQUEMENT `front/src/App.jsx` et `front/src/App.css`. Ne touche pas au backend (il est déjà fini et fonctionnel).
- Garde le code en français, commenté, cohérent avec le style existant du fichier.
- Ne casse pas les modes existants (recherche, candidatures).

## VÉRIFICATION (fais-le toi-même)
1. `cd front && npm run build` doit passer sans erreur ni warning bloquant.
2. Relis ton diff pour confirmer : nouveau bouton sidebar présent, PostuleesView branchée sur activeMode==='postulees', compteur dynamique correct, tri par relance, badge "à relancer" si date dépassée.
Rapporte en français ce que tu as modifié et le résultat du build.
