# Évaluation des CV et version ATS

Le projet ne prétend pas reproduire la note interne d'un logiciel de recrutement. Chaque entreprise configure son ATS différemment. Le résultat produit ici est un indicateur interne, explicable et reproductible.

## Les cinq dimensions

| Dimension | Résultat | Signification |
|---|---|---|
| Éligibilité | `pass`, `fail`, `review` | Vérifie les critères explicitement éliminatoires présents dans l'annonce. Une information absente reste à vérifier. |
| Parsing | `pass`, `fail` | Relit le PDF ATS et vérifie que les champs essentiels sont extractibles. |
| Correspondance | 0–100 | Mesure les compétences, expériences, contexte métier, formations et contraintes prouvés par le profil maître. |
| Qualité humaine | 0–100 | Mesure pertinence, clarté, preuves, concision et aptitude à la mise en page. |
| Véracité | `pass`, `fail` | Bloque les expériences, compétences et affirmations absentes de la source de vérité. |

Le statut global est `ready`, `review` ou `blocked`. Un contrôle en échec bloque la validation. Une donnée inconnue produit `review`, jamais un faux échec.

## Pondérations initiales

La correspondance utilise la configuration versionnée `config/cv_assessment.json` :

- compétences obligatoires : 35 % ;
- expériences prouvées : 30 % ;
- métier et contexte : 15 % ;
- formation et certifications : 10 % ;
- contraintes : 10 %.

Les seuils `strong`, `credible`, `weak` et `poor` sont des catégories internes. Ils ne correspondent pas à une note visible dans Workday, Greenhouse, Oracle ou un autre ATS.

## Fichiers produits

- `cv_ats.pdf` et `cv_ats.html` : version mono-colonne, sans photo ni mise en page complexe ;
- `cv_final.pdf` et `cv_final.html` : version design destinée à la lecture humaine ;
- `cv_final.json` : contenu structuré du CV ;
- `cv_assessment.json` : évaluation détaillée ;
- fichiers JSON intermédiaires : traçabilité des agents et contrôles.

Les nouvelles générations ne produisent plus de fichiers Markdown ni de fichier de copie Canva.

## Limites

Les questions posées dans le formulaire de candidature peuvent déclencher un rejet externe et ne figurent pas toujours dans l'annonce. Le système ne peut donc pas garantir le passage d'un ATS. Il ne doit pas déduire qu'un refus provient automatiquement du CV ou de l'ATS.

La calibration future doit utiliser des résultats observables : candidature envoyée, réponse humaine, entretien obtenu et motif de refus connu. Les pondérations ne doivent être ajustées qu'après plusieurs cas comparables.

## Compatibilité

Les anciens dossiers contenant uniquement `quality_score` et `ats_score` restent lisibles dans l'interface. Ces champs sont temporairement dérivés des nouvelles dimensions pour les nouvelles générations et pourront être retirés après migration des dossiers utiles.
