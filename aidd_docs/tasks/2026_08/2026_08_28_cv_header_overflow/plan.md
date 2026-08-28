---
objective: "Empêcher le débordement des sous-titres, faire détecter l'erreur par le vérificateur et fiabiliser les faits Konexio et médiation numérique."
status: implemented
---

# Plan: Sous-titre multi-lignes et profil médiation numérique

## Phases

| # | Phase | File |
|---|---|---|
| 1 | Règle commune de retour à la ligne et contrôle qualité | [`phase-1.md`](./phase-1.md) |
| 2 | Correction des données Konexio et enrichissement IA | [`phase-2.md`](./phase-2.md) |

## Critères d'acceptation

- Un sous-titre trop large est séparé en deux lignes dans le PDF et le HTML.
- Le vérificateur signale un sous-titre qui dépasserait la largeur imprimable.
- Konexio est daté de janvier 2023 à juillet 2023.
- La variante médiation/formateur mentionne les connaissances IA déjà présentes dans le CV maître.
- Les tests passent et un PDF de contrôle ne présente aucun débordement.
