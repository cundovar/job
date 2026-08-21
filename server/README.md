# Backend — Serveur de candidatures

Backend Node/Express (ESM) qui gère le statut des candidatures et les persiste sur disque,
au même format que le tracker Python.

## Démarrage

```bash
# Terminal 1 — Backend (port 3001)
cd server
npm install
npm start        # ou "npm run dev" pour le rechargement automatique

# Terminal 2 — Frontend (port 5173)
cd front
npm run dev
```

## Endpoints

| Méthode | Endpoint                             | Description                      |
|---------|--------------------------------------|----------------------------------|
| GET     | `/api/health`                        | Vérifie que le serveur tourne    |
| GET     | `/api/applications`                  | Liste toutes les candidatures    |
| POST    | `/api/applications/:id/applied`      | Marque une candidature postulée  |
| POST    | `/api/applications/:id/not-applied`  | Annule le statut "postulé"       |

## Architecture — Pattern Repository

Les routes ne connaissent que l'interface `applicationsRepository.js`.
Pour passer à une base de données, crée `sqlApplicationsRepository.js`
et change une seule ligne dans `index.js`.

## Fichiers de données

- **Lecture** : `front/public/data/candidatures.json` (jamais modifié)
- **Écriture** : `data/applications_tracker.json` (même format que le tracker Python)
