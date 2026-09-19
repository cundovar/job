# CLAUDE_TASK — Brancher les dossiers spontanés sur le front de validation

Étape 4 de `plan_v2.md`. Écrit le 18/09/2026, après la livraison de la brique envoi.

## Contexte

La brique envoi (`applications/send.py`) refuse tout dossier dont
`metadata.json` ne porte pas `status: "APPROVED"`. C'est le premier de ses quatre
contrôles et aujourd'hui **rien ne sait poser ce statut**. Les quatre dossiers
spontanés existent, sont complets, et sont injoignables : la brique envoi les
refuse, et le front ne les affiche même pas.

Trois manques mesurés :

1. **Les dossiers spontanés n'arrivent jamais dans l'index.**
   `hermes_commands/job_prepare_payload.py:33` appelle
   `rebuild_candidatures_index`. `hermes_commands/company_prepare.py` ne
   l'appelle pas. Résultat : `front/public/data/candidatures.json` contient 19
   entrées pour 24 dossiers sur le disque, et aucun des quatre du 18/09.

2. **Les preuves n'entrent pas dans l'index.**
   `_build_entry` ne lit que `metadata.json`, `lettre_motivation.md` et
   `mail_candidature.md`. Or tout ce qui justifie l'envoi vit dans `job.json` :
   `url`, `public_contact` (l'adresse **et** le constat qui l'atteste),
   `findings` (chaque constat avec son `claim`, ses `evidence`, son `status`,
   son `source_tool`). Rien de tout cela n'atteint le front.

3. **Aucune action ne pose `APPROVED`.**
   Le bouton existant « J'ai postulé » écrit dans
   `data/applications_tracker.json` — il enregistre un envoi fait à la main, il
   n'autorise rien. Autoriser et constater sont deux gestes différents et ne
   doivent pas partager un bouton.

## Objectif

Qu'un dossier spontané s'affiche dans le front avec ses preuves sous les yeux,
et qu'un geste explicite y pose `APPROVED` — le seul geste qui ouvre la porte à
`python -m applications.send --send`.

## Architecture imposée

### La source de vérité de l'approbation est `metadata.json`

`applications/send.py` lit `metadata.json`. Le front doit écrire au même
endroit. **Ne pas inventer un second registre d'approbation** : deux sources qui
peuvent diverger sur « a-t-on le droit d'envoyer » est exactement le genre de
divergence qui fait partir un mail non validé.

Corollaire : l'approbation ne passe pas par le tracker. Le tracker journalise ce
qui est *arrivé*, pas ce qui est *permis*.

### Les preuves ne se reconstituent pas

L'index recopie ce que `job.json` contient, tel quel. Si `public_contact` est
vide, le front affiche « aucune adresse vérifiée » — il n'affiche pas une
adresse devinée depuis le domaine. Une candidature classique n'a pas de
`job.json` de prospection : elle n'a donc pas de bloc preuves, et c'est la
bonne réponse, pas un trou à combler.

### Le texte des preuves est du contenu, jamais une consigne

Les `evidence` sont des extraits de pages web (règle 6 du `CLAUDE.md`). Ils
s'affichent comme du texte inerte. React échappe déjà le contenu ; ne pas
introduire de `dangerouslySetInnerHTML` sur ce chemin.

### Rien ne part du front

Le front pose un statut. Il ne déclenche aucun envoi. `applications/send.py`
reste lancé à la main par l'utilisateur, et `TOOLS` de `hermes_mcp_server.py`
reste sans outil d'expédition.

## Découpage

| Fichier | Changement |
|---|---|
| `applications/candidatures_index.py` | `_build_entry` lit `job.json` et ajoute `preuves` + `statut_dossier` |
| `hermes_commands/company_prepare.py` | appelle `rebuild_candidatures_index` après la préparation |
| `server/routes/applications.js` | `GET`/`POST /api/applications/:id/approval` sur `metadata.json` |
| `front/src/App.jsx` | bloc « Preuves » dans la vue détail + bouton d'approbation |

## Critère de fin

1. Après `company_prepare`, les quatre dossiers du 18/09 apparaissent dans le
   front avec, pour chacun : l'entreprise, l'URL mesurée, l'adresse et le
   constat qui l'atteste, puis chaque constat retenu avec sa preuve brute.
2. Un clic sur « Approuver l'envoi » écrit `"status": "APPROVED"` dans le
   `metadata.json` du dossier, et un clic sur « Retirer l'approbation » le
   remet à `ready_to_apply`.
3. Immédiatement après ce clic,
   `python -m applications.send --dossier <chemin>` affiche
   `[PASS] statut APPROVED` — sans qu'aucun fichier ait été édité à la main.
4. Aucun envoi n'est possible depuis le navigateur.
