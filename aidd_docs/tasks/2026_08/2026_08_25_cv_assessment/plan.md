---
objective: "Chaque CV généré expose des contrôles d’éligibilité, parsing et véracité, des scores séparés de correspondance et de qualité, ainsi qu’une version ATS vérifiée distincte du CV graphique."
status: implemented
---

# Plan: Évaluation CV réaliste et export ATS

## Overview

| Field      | Value |
| ---------- | ----- |
| **Goal**   | Remplacer la note ATS unique par une évaluation explicable, vérifiable et affichée dans les deux parcours de génération. |
| **Source** | Demande utilisateur du 25 août 2026 dans cette conversation |

## Phases

| #   | Phase | File |
| --- | ----- | ---- |
| 1 | Modèle d’évaluation et calcul déterministe | [`phase-1.md`](./phase-1.md) |
| 2 | Export ATS et validation du parsing | [`phase-2.md`](./phase-2.md) |
| 3 | Exposition backend et interface des résultats | [`phase-3.md`](./phase-3.md) |
| 4 | Compatibilité, cas étalons et documentation | [`phase-4.md`](./phase-4.md) |

## Resources

| Source | Verified |
| ------ | -------- |
| https://doc.workday.com/admin-guide/en-us/human-capital-management/recruiting/candidates/candidate-skills-match/bmj1604095304483.html | Les compétences obligatoires ont plus de poids et le résultat réel dépend du moteur ATS. |
| https://support.greenhouse.io/hc/en-us/articles/200989175-Unsuccessful-resume-parse | Les colonnes, images, tableaux, en-têtes et pieds de page peuvent dégrader le parsing. |
| https://support.greenhouse.io/hc/en-us/articles/360000653472-Auto-reject | Les réponses aux questions de candidature peuvent déclencher un rejet automatique. |
| https://docs.oracle.com/en/cloud/saas/talent-management/farqa/evaluate-candidate-applications-using-ai-matching-ratings.html | Les moteurs peuvent évaluer séparément formation, expérience et compétences. |
| https://pypdf.readthedocs.io/_/downloads/en/5.4.0/pdf/ | `pypdf` permet une vérification locale reproductible du texte réellement extractible du PDF. |

## Decisions

| Decision | Why |
| -------- | --- |
| Séparer éligibilité, parsing, correspondance, qualité humaine et véracité | Une note unique mélange des contrôles bloquants et des critères graduels qui n’ont pas la même signification. |
| Laisser Python calculer les statuts et scores finaux à partir de preuves structurées | Le LLM peut analyser et expliquer, mais ne doit pas être l’autorité finale sur les seuils ou la véracité. |
| Représenter une donnée absente par `review`, jamais par un échec implicite | Une annonce ou un profil incomplet ne doit pas provoquer un faux rejet. |
| Conserver `cv_final.pdf` et ajouter `cv_ats.pdf` | Le CV graphique reste utile à la lecture humaine tandis que la version mono-colonne cible le parsing. |
| Arrêter de générer les sorties Markdown et Canva | Le PDF design est produit directement par le code ; aucun copier-coller manuel dans Canva n’est requis. |
| Maintenir temporairement `quality_score` et `ats_score` comme champs de compatibilité documentés | Les candidatures historiques et l’interface existante restent lisibles pendant la migration. |
