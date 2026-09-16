# Codebase Audit: `cv_generator/`

Le pipeline protège correctement la vérité du CV, mais il neutralise une partie du jugement éditorial, mesure mal la contrainte d'une page et exporte même lorsque la dernière revue demande encore une révision.

- **Date**: 2026-08-27
- **Scope**: `cv_generator/`
- **Health**: good
- **Findings**: 0 critical, 4 warning, 1 minor

## Findings

| Sev | Category | Location | Issue | Suggested fix | Effort |
| --- | --- | --- | --- | --- | --- |
| 🟡 | code-quality | `cv_generator/ai_agents.py:396` | Le plan conserve une priorité éditoriale pour chaque expérience, puis le tri chronologique de `ai_agents.py:416` l'écrase. La révision reconstruit ensuite le CV dans cet ordre de plan (`ai_agents.py:512`), ce qui empêche l'agent de placer en premier l'expérience la plus pertinente pour l'annonce. | Trier d'abord par pertinence/priorité, avec la récence comme critère secondaire, et autoriser le réviseur à réordonner les identifiants validés. | M |
| 🟡 | code-quality | `cv_generator/pipeline.py:37` | La dernière revue est calculée mais n'a aucun effet sur la suite : le PDF est exporté à `pipeline.py:69` et le résultat renvoie toujours `ok: True` à `pipeline.py:78`, même avec `needs_revision`. | Conditionner l'export final à un statut acceptable ou renvoyer explicitement un brouillon non prêt ; prévoir une boucle de révision bornée lorsque des problèmes élevés subsistent. | M |
| 🟡 | code-quality | `cv_generator/cv_assessment.py:254` | `layout_readiness` vaut 100 dès que le nombre d'expériences respecte la limite. Le nombre réel de pages, pourtant disponible dans `parseability.page_count`, n'entre pas dans ce score. Un PDF de deux pages peut donc recevoir 100/100 en préparation de mise en page. | Intégrer `page_count <= max_pages` dans la qualité humaine et rendre le dépassement bloquant ou au minimum non prêt. | S |
| 🟡 | code-quality | `cv_generator/exporters.py:397` | L'exporteur concatène systématiquement la description du projet et toute la liste des technologies ; la même logique est répétée à `exporters.py:502`. Lorsque la description cite déjà n8n, MCP ou WordPress, le PDF répète immédiatement ces mots. | Centraliser le rendu du projet et supprimer les technologies déjà présentes dans la description après normalisation. | S |
| 🟢 | code-quality | `cv_generator/exporters.py:452` | Les carrés visibles devant les coordonnées ne sont pas un problème de police : le PDF dessine volontairement un rectangle pour chaque ligne de contact, sans distinction sémantique. | Remplacer ces rectangles par des pictogrammes vectoriels cohérents avec le modèle ou supprimer les marqueurs. | S |

## Top actions

1. Faire respecter la dernière revue avant de publier un fichier `cv_final` ; cela résout le risque principal de livrer un CV explicitement marqué `needs_revision`.
2. Préserver l'ordre de pertinence produit par l'analyse au lieu de le remplacer par un ordre strictement chronologique.
3. Rendre la contrainte d'une page mesurable et bloquante, puis dédupliquer le bloc projet et corriger les marqueurs de contact.

## Coverage

- **Scanned**: code-quality (`cv_generator/`, pipeline, agents, assessment et exporteurs)
- **Skipped**: architecture, security, dependencies, performance, tests et ui — hors du pilier demandé pour ce passage ciblé
