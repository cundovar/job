---
status: done
---

# Instruction: File backend, suivi frontend et non-régression

## Architecture projection

```txt
.
├── server/routes/applications.js     ✏️ tâches agence et endpoint de statut
├── front/src/App.jsx                 ✏️ polling résilient après HTTP 202
└── tests/test_deployment_contract.py ✏️ contrat asynchrone de production
```

## Tasks to do

1. Mettre la mesure et la préparation dans une file en mémoire et répondre immédiatement.
2. Exposer le statut d'une tâche agence et dédupliquer les demandes par domaine.
3. Suivre la tâche côté interface avec une tolérance aux erreurs réseau transitoires.
4. Couvrir le contrat par un test et construire l'image Docker complète.

## Test acceptance criteria

| Task | Acceptance criteria |
| --- | --- |
| 1 | `POST /api/agencies/target` répond 202 sans attendre les scripts Python. |
| 2 | Une relance du même domaine retourne la tâche active et un endpoint permet d'en lire l'état. |
| 3 | L'interface attend `completed`, remonte l'erreur backend et tolère cinq erreurs réseau consécutives. |
| 4 | Les tests ciblés, le build frontend et les imports Python de l'image passent. |
