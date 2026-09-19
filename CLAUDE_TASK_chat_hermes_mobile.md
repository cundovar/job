# CLAUDE_TASK_chat_hermes_mobile.md

## Contexte
Le chat Hermes (front/src/HermesChat.jsx + HermesChat.css, monté dans App.jsx via `<HermesChat />`) fonctionne en desktop, mais a deux bugs en MOBILE (mobile-first). Le backend/proxy (`server/routes/hermes.js`, `/api/hermes/*`) est OK — ne pas y toucher.

## Bug 1 — Le bouton flottant « 💬 Hermes » chevauche « Lancer une recherche » (mobile)
- Il existe DEUX boutons flottants `position: fixed` en bas à droite, tous deux visibles en mobile en mode « recherche » :
  - `.fab` (App.css ~ligne 438) : « Lancer une recherche », `bottom: calc(var(--bottom-nav-h) + var(--safe-b) + var(--sp-3))`, `z-index: 25`.
  - `.hermes-fab` (HermesChat.css ~ligne 3) : « 💬 Hermes », `bottom: calc(var(--bottom-nav-h) + var(--safe-b) + var(--sp-4))`, `z-index: 50`.
- Le `.hermes-fab` (z-index plus haut) recouvre le `.fab`. Il faut repositionner le FAB Hermes (et si besoin son panneau) pour ne masquer AUCUN élément interactif (bouton « Lancer une recherche », bottom-nav, etc.) en mobile, sans casser le desktop (≥768px, sidebar visible, `.fab` masqué).

## Bug 2 — Dans le panneau, le textarea n'affiche pas le texte tapé et l'envoi ne part pas (mobile)
- `.hermes-panel` (HermesChat.css ~ligne 27) est `position: fixed; height: 70vh; bottom: calc(... + 56px)`.
- En mobile (petit viewport + clavier virtuel), la zone de saisie est probablement hors-champ / recouverte : le textarea (HermesChat.jsx lignes 115-126, `value={input}` + `onChange`) ne reçoit pas l'input → `input` reste vide → le bouton d'envoi reste `disabled`.
- La logique React est correcte ; c'est un problème de layout/z-index/position/hauteur en mobile (gestion du clavier, `svh` vs `vh`, recouvrement).
- Fix attendu : panneau pleinement utilisable en mobile (hauteur adaptée, saisie visible, envoi fonctionnel, pas de recouvrement par la bottom-nav ou le clavier).

## Contraintes
- Mobile-first. Réutiliser les variables CSS existantes (index.css : `--bottom-nav-h`, `--safe-b`, `--sp-*`, `--tap`, `--r-*`, etc.).
- Ne pas casser le desktop.
- Ne pas toucher au backend (server/), ni au proxy `/api/hermes/*`.
- Pas de nouvelle dépendance npm.
- Commentaires en français, identifiants en anglais.

## Vérifications demandées
1. `cd front && npm run build` doit passer sans erreur.
2. Raisonner le rendu mobile : le FAB Hermes ne recouvre plus « Lancer une recherche », le textarea affiche la saisie et l'envoi fonctionne.
3. Ne pas laisser de doublon de processus serveur sur le port 3001.

## Rapport final (en français)
Fichiers modifiés + corrections apportées + résultats des vérifications.
