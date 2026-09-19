# Plan — ce qui reste à faire

Écrit le 18/09/2026, après l'implémentation de la voie candidature spontanée. Remplace `plan_v1.md`, qui décrivait un travail désormais fait.

## État actuel

La voie spontanée fonctionne. Quatre entreprises produisent un dossier ; le Vérificateur a dégradé 4 constats sur 15, tous à raison, et n'a jamais promu un constat. `company_top` et `company_prepare` sont exposés à Hermes ; `tools/list` renvoie 7 outils, aucun d'expédition. La suite de tests passe de 122 à 136 succès.

Un défaut bloquant : la génération de CV échoue sur les deux voies.

---

## Étape 1 — Réparer la génération de CV  *(bloquant)*

`prepare_custom_cv` échoue avec `CVAgentError`. Diagnostic posé : le budget `max_tokens` du rôle CV est épuisé par le raisonnement du modèle avant qu'il émette du contenu, et la réponse revient vide.

1. Monter le budget de tokens sur le seul rôle `deepseek_cv` dans `config/ai_role_routing.json`, et relancer. Ce fichier sépare déjà `deepseek_cv` de `deepseek_job`, donc le reste n'est pas touché.
2. Si la réponse reste vide, la cause est ailleurs — regarder ce que renvoie réellement le client avant l'exception.
3. Dans les deux cas : **faire parler l'erreur.** Une réponse vide doit remonter en « budget épuisé avant émission de contenu », pas en `CVAgentError` opaque. Une erreur qu'on lit vaut mieux qu'une erreur qu'on débogue.
4. Vérifier l'hypothèse que tout ou partie des 17 échecs pré-existants tombent avec le même correctif.

Critère de fin : les quatre dossiers sortent complets, CV compris.

---

## Étape 2 — Lire les quatre dossiers  *(le vrai test)*

Ce n'est pas du code. C'est la seule question qui compte : **est-ce que tu les enverrais ?**

Pour chacun, vérifier trois choses séparément :

- les constats sont-ils vrais — c'est le Vérificateur qui est jugé ;
- le CV retenu est-il le bon — c'est la sélection de variante qui est jugée ;
- le message sonne-t-il juste — c'est le Rédacteur qui est jugé.

Ces trois verdicts sont indépendants. Des constats justes avec un message qui sonne faux est un problème de consignes du Rédacteur, pas du Vérificateur. Ne pas corriger la mauvaise brique.

Optionnel, une ligne de CSV : ajouter une entreprise dont le site ne dit presque rien, pour voir le système refuser de produire. C'est le comportement qui protège le jour d'un envoi en volume, et le seul qui n'a pas encore été observé.

---

## Étape 3 — La brique envoi  *(le prochain vrai chantier)*

Mérite son propre `CLAUDE_TASK`. C'est la seule partie du système dont les erreurs sont irrattrapables : un email parti est parti.

### Règle d'architecture

L'envoi **n'est jamais un outil Hermes.** Le dictionnaire `TOOLS` de `hermes_mcp_server.py` est la liste des permissions de l'orchestrateur ; aucun outil d'expédition n'y entre. L'envoi se déclenche depuis le front de validation ou par une commande que seul l'utilisateur lance.

### Ordre des contrôles, non négociable

```
statut APPROVED
      ↓
DO_NOT_CONTACT        (prioritaire sur tout le reste)
      ↓
déduplication par entreprise
      ↓
quota du jour
      ↓
envoi
      ↓
journalisation
```

`DO_NOT_CONTACT` est déjà vérifié avant la collecte. Le revérifier ici est une double barrière assumée : entre la collecte et l'envoi, il peut s'être passé des jours.

### Contenu de la brique

- Envoi réel, avec pièce jointe ou lien — décision à prendre : une pièce jointe sur un premier contact pèse sur la délivrabilité, un lien se suit mais paraît moins direct.
- Domaine d'envoi authentifié : SPF, DKIM, DMARC. Sans cela tout finit en indésirables, quelle que soit la qualité du message.
- Volume très faible au démarrage, qui monte lentement.
- Gestion des rebonds, et désinscription immédiate et définitive sur simple demande.
- Identité de l'expéditeur claire.

### Préparer la boucle de retour dès maintenant

Le journal d'envoi doit porter, dès le premier envoi, les champs qui serviront plus tard à calibrer : quel dossier exact est parti, à qui, quand, et ensuite réponse reçue, entretien obtenu, refus et son motif.

Ces champs coûtent dix minutes maintenant et sont impossibles à reconstituer après coup. C'est la seule raison pour laquelle l'étape 6 existe.

### À vérifier avant la première vraie salve

Les règles applicables à la prospection par email en France et les conditions du fournisseur d'envoi pour cet usage. Comme le dit la section 10 de la spec, ces règles évoluent et ne se déduisent pas d'une architecture.

---

## Étape 4 — Brancher les dossiers sur le front de validation

Le front lit `front/public/data/candidatures.json`. Les dossiers spontanés doivent y arriver au même format, avec **les preuves affichées à côté du brouillon** : l'entreprise, l'URL, l'adresse et sa source, les constats retenus, leurs preuves, puis le message.

C'est la section 9 de la spec. Sans les preuves affichées, valider devient un acte de foi et l'écran ne sert plus à rien.

---

## Étape 5 — Les relances

`job_relance` existe pour les annonces, avec une échéance à sept jours. Une candidature spontanée se relance autrement : pas de date de clôture, pas de processus en cours, un rythme plus lent et une relance qui doit apporter quelque chose plutôt que répéter.

Adaptation, pas réécriture.

---

## Étape 6 — La boucle de retour

C'est ce qui ferait passer le système de « générateur » à « quelque chose qui s'améliore ». Le `docs/CV_ASSESSMENT.md` du dépôt le dit déjà : la calibration doit se faire sur des résultats observables — candidature envoyée, réponse humaine, entretien obtenu, motif de refus connu.

Tant que rien ne remonte, les pondérations du `cv_assessment` restent des suppositions.

Ne devient possible qu'une fois l'étape 3 faite et quelques dizaines d'envois écoulés. Les pondérations ne s'ajustent qu'après plusieurs cas comparables — le dépôt le dit aussi.

---

## Étape 7 — La mission `web_prospection`

L'autre moitié de la spec. Les sources changent, la liste des contrôles change, le ton du Rédacteur change. Le moteur ne bouge pas.

C'est là seulement que Lighthouse et les outils d'audit de site — `check_links`, `inspect_forms`, `mobile_structure_check` — trouvent leur usage.

---

## Ce qui ne change jamais

- Pas de preuve mesurée, jamais de `CONFIRMED`.
- Zéro constat confirmé, rien n'est produit. Pas de repli générique.
- Seuls les `CONFIRMED` entrent dans la `description` de l'`opportunity`, parce que ce champ devient la vérité de référence du CV.
- Le profil maître est la seule source de vérité sur le candidat. `data/` n'est jamais commité.
- Aucun outil d'envoi dans `TOOLS`.
- Une donnée inconnue produit `UNCERTAIN` ou `review`, jamais un faux échec.

## Ordre

Les étapes 1 et 2 se font dans la journée. L'étape 3 est le prochain chantier et mérite son brief. Les étapes 4 à 7 ne sont pas séquentielles : 4 et 5 sont du confort, 6 dépend de 3, 7 est indépendante.
