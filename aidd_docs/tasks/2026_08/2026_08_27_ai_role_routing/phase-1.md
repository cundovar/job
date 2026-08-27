---
status: done
---

# Phase 1: Transport du modèle et du niveau de raisonnement

1. Étendre le client Unix avec `preferred_model` et `reasoning_effort`.
2. Valider ces valeurs côté serveur avant exécution.
3. Appliquer le modèle à Codex ou Claude et l’effort uniquement à Codex.
4. Conserver la compatibilité des appels existants.

## Acceptation

- Une requête valide atteint le fournisseur avec ses options.
- Une valeur non autorisée est rejetée sans exécuter de CLI.
- Les appels sans options gardent le comportement précédent.
