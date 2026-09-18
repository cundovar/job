# CLAUDE_TASK — La brique envoi

## Contexte

La voie spontanée produit des dossiers complets et vérifiés : lettre datée par le système, mail au ton spontané, CV adapté, évaluation à cinq dimensions. Rien, dans le système, n'envoie encore quoi que ce soit à une entreprise — `notifications/email_sender.py` n'écrit qu'à l'utilisateur lui-même (relance quotidienne, gated `--send-outputs`) et ne préjuge de rien ici.

L'envoi est la seule partie du système dont les erreurs sont irrattrapables : un email parti est parti. C'est aussi la seule qui transforme le système de « générateur » en « machine à candidater » — la boucle de retour (étape 6 du plan) n'existera que si des envois réels partent et que leur issue est journalisée.

## Objectif (scope serré)

Un module Python qui prend **un** dossier au statut `APPROVED`, applique la chaîne de contrôles dans l'ordre imposé, envoie via un fournisseur derrière une interface, et journalise l'envoi avec les champs de la boucle de retour. Déclenché uniquement par une commande CLI que seul l'utilisateur lance.

## Non-objectifs

- Pas d'outil Hermes : jamais d'entrée dans le dictionnaire `TOOLS` de `hermes_mcp_server.py`.
- Pas d'endpoint front ni de bouton : le front viendra avec l'étape 4.
- Pas de relance : c'est l'étape 5.
- Pas de warm-up de domaine, pas de gestion de campagne : un envoi à la fois, à la main.

## Architecture imposée

### L'ordre des contrôles, non négociable

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

Chaque contrôle refusant produit un motif explicite, jamais une exception nue. `DO_NOT_CONTACT` est déjà vérifié avant la collecte ; le revérifier ici est une double barrière assumée — entre la collecte et l'envoi, il peut s'être passé des jours.

### Défaut sec

Aucun envoi réel sans drapeau explicite (`--send` ou équivalent). Sans lui, la commande exécute toute la chaîne de contrôles et affiche ce qui partirait, à qui, avec quelle pièce — et n'envoie rien. Ce défaut est la règle 4 du `CLAUDE.md` appliquée à la brique : ne jamais l'inverser.

### Interface fournisseur

- Une classe abstraite type `EmailSender` (module `applications/` ou `mailing/`, au choix de la session) : `send(to, subject, body, attachment=None) -> SendResult`.
- Une implémentation SMTP réelle, un fake en tests. **Zéro appel réseau en test.**
- Le fournisseur et ses identifiants viennent de variables d'environnement, jamais en dur.

### Journal

Étendre `data/applications_tracker.json` **sans casser son format** (règle 5 : il est lu par un cron Python et le serveur Node ; un record `applied` garde au minimum `status`, `applied_at`, `follow_up_at`, `job_title`, `company`, `key`, `created_at`, `updated_at`). Ajouter, jamais retirer :

- dès l'envoi : chemin exact du dossier, destinataire **et source de l'adresse** (laquelle des deux sources l'a établie), horodatage, fournisseur, identifiant de message ;
- pour plus tard : réponse reçue, entretien obtenu, refus et son motif. Ces champs coûtent dix minutes maintenant et sont impossibles à reconstituer après coup — c'est la seule raison pour laquelle l'étape 6 du plan existe.

Un échec d'envoi se journalise aussi : statut d'échec + motif, pour ne jamais retenter à l'aveugle.

## Part code / part infrastructure

### Part code — ce chantier

1. Le module d'envoi : chaîne de contrôles, interface fournisseur, implémentation SMTP, fake.
2. La commande CLI utilisateur : un dossier en argument, défaut sec, sortie lisible (chaque contrôle : pass/refus+motif).
3. Le journal étendu dans le tracker + tests de non-régression sur le format existant.
4. Tests : chaque contrôle refusant son motif, le fake fournisseur, le chemin `--send`, et un test contrat sur le format du tracker.

### Part infrastructure — hors dépôt, prérequis avant la première salve réelle

À faire à la main, par l'utilisateur ; le code n'en dépend que par la configuration :

1. Domaine d'envoi authentifié : SPF, DKIM, DMARC. Sans cela tout finit en indésirables, quelle que soit la qualité du message.
2. Compte fournisseur d'envoi, avec ses conditions d'usage pour de la prospection.
3. Vérification des règles applicables à la prospection par email en France — ces règles évoluent et ne se déduisent pas d'une architecture (section 10 de la spec).
4. Stratégie de volume : très faible au départ, montée lente. Le quota du jour (point de configuration) doit commencer à 1 ou 2.
5. Gestion prévue dès le premier envoi : rebonds, et désinscription immédiate et définitive sur simple demande.

## Décisions ouvertes

À trancher avant le premier envoi réel ; elles ne bloquent pas l'écriture du code si l'interface fournisseur reste abstraite :

- **Pièce jointe vs lien.** Une pièce jointe sur un premier contact pèse sur la délivrabilité ; un lien se suit mais paraît moins direct. Recommandation : lien (portfolio + CV en ligne), pièce jointe derrière une option.
- **Fournisseur d'envoi.** SMTP générique ou service dédié ; la décision dépend des conditions d'usage de la part infrastructure.
- **Adresse expéditrice.** Sur le domaine authentifié, identité claire (prénom nom).

## Critère de fin

1. `pytest tests/` au même état qu'avant le chantier, plus : tests verts sur chaque contrôle refusant, le fake fournisseur, le chemin `--send`, le format du tracker.
2. Un dry-run sur un vrai dossier du 18/09 affiche la chaîne complète de contrôles avec leurs verdicts et n'envoie rien.
3. La commande sans `--send` n'établit **aucune** connexion sortante — vérifié par test.
4. Le journal d'un envoi simulé (fake) porte tous les champs de la boucle de retour.
