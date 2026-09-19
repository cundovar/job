# TASK : Bouton « Retenir & préparer » sur les cards d'agences

## Contexte

Projet job-search-automation-package (front React/Vite `front/`, backend Express `server/`).
L'onglet 🏢 Agences du front liste des agences découvertes (`front/public/data/agencies/latest.json`,
champs : name, website, score, stack, emails, query, reasons). Aujourd'hui elles sont juste affichées.

On veut : un **bouton dans chaque card** qui déclenche le circuit de candidature spontanée :
1. L'utilisateur clique → l'agence est ajoutée aux fichiers de ciblage (son clic = sa décision).
2. Mesure réelle du site : `python3.10 -m hermes_commands.company_top --refresh` (cwd = racine projet).
3. Si l'agence est exploitable (numérotée `N.` dans la sortie) : génération du dossier
   `python3.10 -m hermes_commands.company_prepare <N>` → lettre + mail + CV adapté,
   qui apparaît dans `front/public/data/candidatures.json` (onglet Spontanées du front).
4. La validation/approbation reste HUMAINE via le front — le backend n'écrit JAMAIS
   dans `output/applications/*/metadata.json` ni ne modifie un statut.

## Interpréteur Python

**Toujours `python3.10`** (jamais `python3` : bs4 absent). Le CLI marche :
`cd /home/cundo/Bureau/perso/code_perso/job-search-automation-package && python3.10 -m hermes_commands.company_top`

## Format de sortie de company_top (à parser)

```
Prospection spontanee — 4 structure(s)

1. Agence LIMITE
   Poste vise : Développeur web / Intégrateur
   URL : https://agence-limite.fr
   Constats confirmes : 3
   - <constat 1>
   ...
2. L'agence RUP
...
```
- Entreprises exploitables : numérotées `N. <Nom>`.
- Entreprises refusées : ligne `-. <Nom> : REFUS. <motif>` (format exact à vérifier sur une vraie sortie ; matcher le nom).

## Backend — `server/index.js` (nouvelle route)

`POST /api/agencies/target` — body JSON `{ domain: "amphibee.fr", dry: false }`

1. Normaliser `domain` (minuscules, sans protocole ni www, sans chemin). Valider ; sinon 400.
2. Charger `front/public/data/agencies/latest.json` → trouver l'agence dont `website` contient
   ce domaine. Introuvable → 404 JSON.
3. **Idempotence** : si `config/companies.csv` contient déjà une ligne dont la colonne `site`
   inclut ce domaine → ne rien réécrire ; passer direct à l'étape mesure avec `already_targeted: true`.
4. Sinon, ajouter en **append-only** (sans réécrire/reformater le reste) :
   - `config/companies.csv` : ligne `"<nom>",https://<domain>,,agence_com_engagee,a_qualifier,`
     (échappement CSV correct si le nom contient une virgule ou un guillemet ; garantir le \n final).
   - `config/companies.yaml` : bloc dans la liste `companies:` (même indentation/schema que les
     entrées existantes, cf. le bloc « Agence Jaam ») :
     ```yaml
       - nom: <name>
         type: agence_com_engagee
         zone: Ile-de-France
         taille_estimee: null
         taille_verifiee: false
         statut: a_qualifier
         notes: "Ajoutée le <AAAA-MM-JJ> via bouton front (découverte Étape 0). URL: https://<domain>. Type et taille non confirmés."
     ```
5. **dry: true** → s'arrêter ici, renvoyer ce qui serait écrit sans rien écrire (pour tests).
6. Mesure : spawn `python3.10 -m hermes_commands.company_top --refresh`, cwd = racine projet,
   timeout 240s, cap stdout. Parser : numéro `N.` + nb constats de l'agence cible (match nom
   insensible à la casse, sinon match URL/domaine dans le bloc). Si ligne REFUS correspondante
   → répondre `{ ok: false, stage: "mesure", reason: "<motif>" }` (c'est un résultat normal).
7. Si exploitée : spawn `python3.10 -m hermes_commands.company_prepare <N>` (timeout 420s).
   Vérifier ensuite que `front/public/data/candidatures.json` contient une entrée dont
   `entreprise` correspond au nom de l'agence AVEC un champ `preuves` non vide.
8. Réponse succès : `{ ok: true, domain, number: N, constats_confirmes: <int>,
   already_targeted: <bool>, dry: false }`.
9. Toutes les erreurs → JSON `{ ok: false, stage, error }` avec codes HTTP propres. Logs console.

Sécurités : ne JAMAIS toucher à `output/applications/**`, jamais de statut APPROVED,
aucune requête sortante vers les sites autres que via les deux commandes python ci-dessus.

## Front — `front/src/App.jsx` (composant AgenciesList, cartes d'agences)

- Bouton par card : libellé « 🎯 Retenir & préparer » (désactivé pendant le traitement DE cette
  card seulement ; les autres restent cliquables).
- Clic → `fetch('/api/agencies/target', { method:'POST', headers:{'Content-Type':'application/json'},
  body: JSON.stringify({ domain }) })` avec `domain` dérivé de `agency.website`
  (`new URL(agency.website).hostname`), protégé par try/catch.
- Affichage d'état dans la card : « ⏳ Mesure du site puis génération CV + lettre (2-5 min)… »
  pendant l'attente ; à la réponse :
  - `ok: true` → bandeau vert « ✅ Dossier prêt — voir l'onglet 🛡 Spontanées » ;
  - `ok: false` → bandeau rouge avec le `reason` ;
  - erreur réseau → bandeau rouge générique.
- Styles cohérents avec les classes existantes du fichier (réutiliser les patterns CSS présents ;
  ajouter un minimum de CSS si nécessaire dans la feuille de style existante).
- Le bouton reste visible après succès mais passe en état « fait » (disabled + libellé
  « ✅ Dossier préparé ») — stocker localement l'état par domaine (useState suffit, pas de persistance).

## Contraintes dures

- NE PAS redémarrer ni tuer les serveurs qui tournent (backend `npm run dev` = node --watch,
  Vite HMR : les modifications sont prises en compte automatiquement).
- NE PAS modifier : `config/companies.csv`/`.yaml` (contenu existant), le schéma de
  `latest.json`, `output/applications/**`, la logique d'envoi (`applications/`).
- Édition append-only des deux fichiers de ciblage, idempotente par domaine.
- Rester minimal : pas de nouvelle dépendance npm, pas de refonte de composant.

## Livrable / tests à exécuter (sans effet de bord business)

1. `curl -s -X POST localhost:3002/api/agencies/target -H 'Content-Type: application/json' -d '{}'` → 400.
2. `curl -s -X POST localhost:3002/api/agencies/target -H 'Content-Type: application/json' -d '{"domain":"inconnu.xyz"}'` → 404 JSON.
3. `curl -s -X POST localhost:3002/api/agencies/target -H 'Content-Type: application/json' -d '{"domain":"agence-limite.fr","dry":true}'` → `{ ok:true, dry:true, ... }` (déjà ciblée → already_targeted, rien écrit).
4. Vérifier après tests : `git diff --stat` (ou ls -l) montre que csv/yaml/latest.json sont inchangés.
5. Rapporter : fichiers modifiés (liste + nb de lignes), résultat des 4 tests.
