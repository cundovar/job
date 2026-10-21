# Bridge IA Codex / Claude sur Netcup

Le générateur utilise un ordre différent pour chaque rôle. La configuration de
référence est `config/ai_role_routing.json` ; le tableau ci-dessous en est
généré et un test vérifie qu'il concorde. Une variable `CV_AI_PROVIDER_ORDER`
définie dans l'environnement remplace cet ordre pour tous les rôles CV.

<!-- routage:debut — généré par `python -m tools.routing_table`, ne pas éditer à la main -->
| Rôle | Ordre d'essai (principal, puis secours) |
|---|---|
| Filtrage des annonces (`job_offer_analyzer`) | deepseek `deepseek-v4-flash` → codex_cli `gpt-5.6-sol` (low) → glm `glm-5.3` |
| Analyse de l'annonce (plan du CV, famille de poste) (`cv_job_analyzer`) | deepseek `deepseek-v4-flash` → codex_cli `gpt-5.6-sol` (low) → glm `glm-5.3` |
| Rédaction du CV (`cv_creator`) | codex_cli `gpt-5.6-terra` (medium) → glm `glm-5.3` → deepseek `deepseek-v4-flash` |
| Vérification de véracité (`cv_truth_checker`) | deepseek `deepseek-v4-flash` → codex_cli `gpt-5.6-sol` (medium) → glm `glm-5.3` |
| Juge qualité (`cv_quality_checker`) | deepseek `deepseek-v4-flash` → codex_cli `gpt-5.6-sol` (medium) → glm `glm-5.3` |
| Correction (révision) (`cv_style_reviser`) | codex_cli `gpt-5.6-terra` (medium) → glm `glm-5.3` → deepseek `deepseek-v4-flash` |
| Lettre de motivation (`agent_redacteur_lettres`) | codex_cli `gpt-5.6-sol` (medium) → glm `glm-5.3` → deepseek `deepseek-v4-flash` |
| Vérification d'entreprise (`company_verifier`) | deepseek `deepseek-v4-flash` → codex_cli `gpt-5.6-sol` (medium) → glm `glm-5.3` |
| Adéquation d'agence (`agency_fit`) | deepseek `deepseek-v4-flash` → glm `glm-5.3` |
<!-- routage:fin -->

Le résumé d'annonce et le mail standard restent entièrement déterministes en
Python. Ils ne consomment aucun appel IA.

## Mesures du routage (22 octobre 2026)

Banc rejoué sur le serveur avec le profil maître réel, sans rien écrire dans le
dépôt : 37 appels IA au total (9 pings, 28 mesures).

- **Analyse de l'annonce**, 3 annonces collées sans titre ni entreprise
  (Coallia, Comptoir des Voyages, mairie d'Argenteuil) : DeepSeek, Codex sol,
  Codex terra et GLM extraient tous correctement famille, entreprise, lieu et
  contrat (le lieu de Comptoir est laissé vide par tous : l'annonce n'en donne
  pas). Durée moyenne : DeepSeek ~40 s, Codex ~60 s, GLM ~130 s.
- **Vérification de véracité**, 2 CV réels avec 3 défauts plantés chacun
  (diplôme inventé, responsabilité inventée sous une référence valide, chiffre
  et certification ajoutés) : tous les fournisseurs qui ont répondu attrapent
  3/3 sur chaque CV, et signalent les mêmes affirmations sur les CV non
  modifiés. DeepSeek reste le plus rapide (19–46 s).
- **Codex sol** a échoué sur 4 appels sur 11 avec `429 Too Many Requests` :
  le quota du modèle sur l'abonnement, pas une panne. Le pont le classe
  désormais en « limite d'utilisation atteinte ». Codex terra n'a pas échoué.
- **Claude CLI** n'est pas authentifié sur le pont : il n'est dans aucune route.

Conséquences : les premiers choix ne changent pas (aucun écart d'exactitude ne
le justifie, et DeepSeek est le plus rapide sur les rôles de contrôle). GLM, de
nouveau disponible, devient le dernier secours des rôles qui n'avaient que
DeepSeek puis Codex sol : une limite Codex ne laisse plus ces rôles sans
fournisseur. La rédaction (CV, révision, lettre) n'a pas été mesurée : elle
demande de générer des CV complets, et rien dans les incidents récents ne
désigne son fournisseur.

## Architecture

Le conteneur Coolify ne reçoit aucun identifiant OAuth. Il communique avec un
service utilisateur exécuté sur l'hôte via un socket Unix privé :

- hôte : `data/.cv_cli_bridge.sock` ;
- conteneur : `/app/data/.cv_cli_bridge.sock` ;
- jeton partagé : `data/.cv_cli_bridge_token` sur l'hôte et
  `/app/data/.cv_cli_bridge_token` dans le conteneur.

Le répertoire `data/` est déjà monté dans Coolify et ignoré par Git. Aucun port
TCP n'est ouvert. Le service n'accepte que des demandes JSON et les commandes
Codex/Claude sont définies dans `tools/cv_cli_bridge.py` : un appelant ne peut
pas fournir une commande shell. Les outils shell, navigateur, MCP et plugins
sont désactivés dans les deux CLI.

### Prérequis Coolify

Le montage doit être un bind mount de l'hôte, pas un volume Docker indépendant :

```text
/home/cundo/apps/job-search-automation-package/data -> /app/data
```

Le service `cundo` et l'utilisateur `node` du conteneur doivent partager le
même UID pour lire le socket et le jeton en mode `0600`. Sur ce VPS, les deux
utilisent l'UID `1000` et ce montage est déjà vérifié.

## Installation du service utilisateur

Depuis le compte `cundo`. Le chemin ci-dessous est celui du VPS ; sur le poste de
travail le dépôt vit dans `~/Bureau/perso/code_perso/job-search-automation-package`.
`tools/cv_cli_bridge.py` déduit désormais sa racine de son propre emplacement, donc
seuls le `cd` et le fichier `.service` sont à adapter.

```bash
cd /home/cundo/apps/job-search-automation-package
test -s data/.cv_cli_bridge_token || openssl rand -hex 32 > data/.cv_cli_bridge_token
chmod 600 data/.cv_cli_bridge_token
mkdir -p ~/.config/systemd/user
install -m 0644 deploy/job-search-cli-bridge.service ~/.config/systemd/user/
mkdir -p ~/.local/share/job-search-cli-bridge/workspace
chmod 700 ~/.local/share/job-search-cli-bridge/workspace
systemctl --user daemon-reload
systemctl --user enable --now job-search-cli-bridge.service
```

Le compte a le mode linger activé, donc le service continue après déconnexion.

## Vérifications

```bash
systemctl --user status job-search-cli-bridge.service
journalctl --user -u job-search-cli-bridge.service -n 50 --no-pager
test -S data/.cv_cli_bridge.sock && echo "socket OK"
```

## Configuration facultative

| Variable | Défaut | Usage |
|---|---|---|
| `CV_AI_PROVIDER_ORDER` | non défini | Surcharge globale désactivant le routage par rôle pour les agents du CV |
| `JOB_AI_PROVIDER_ORDER` | non défini | Surcharge globale du routage du juge d'annonces |
| `AI_CODEX_SOL_MODEL` | `gpt-5.6-sol` | Modèle Codex demandé par les rôles faible, moyen et élevé |
| `AI_CLAUDE_SONNET_MODEL` | `sonnet` | Alias ou nom complet Claude Sonnet |
| `AI_CLAUDE_OPUS_MODEL` | `opus` | Alias ou nom complet Claude Opus 5 |
| `JOB_DEEPSEEK_MODEL` | `deepseek-v4-flash` | Modèle DeepSeek pour le filtrage des annonces |
| `CV_DEEPSEEK_MODEL` | `deepseek-v4-flash` | Modèle DeepSeek pour les secours CV et lettre |
| `CV_CLI_BRIDGE_TIMEOUT_SECONDS` | `300` | Délai maximal par fournisseur CLI |
| `CV_CLI_BRIDGE_CLIENT_TIMEOUT_SECONDS` | `630` | Délai client couvrant Codex puis Claude |
| `CV_CLI_BRIDGE_CODEX_MODEL` | modèle Codex par défaut | Modèle CLI forcé |
| `CV_CLI_BRIDGE_CLAUDE_MODEL` | modèle Claude par défaut | Modèle CLI forcé |
| `CV_CLI_BRIDGE_PROVIDER_ORDER` | `codex,claude` | Ordre interne au service hôte |
| `CV_CLI_BRIDGE_REQUEST_TIMEOUT_SECONDS` | `10` | Délai d'envoi d'une requête socket |
| `CV_CLI_BRIDGE_MAX_CONNECTIONS` | `8` | Connexions socket simultanées maximales |

`DEEPSEEK_API_KEY` est requise pour les étapes ou replis DeepSeek. La clé
`ANTHROPIC_API_KEY` reste facultative car les routes standards utilisent Claude
Code via l'abonnement. L'alias Claude CLI `opus` suit le dernier Opus disponible
sur l'abonnement ; il représente ici Claude Opus 5.

## Reconnexion Claude Code

Si le journal indique que la session OAuth Claude a expiré, ouvrir une session
SSH interactive en tant que `cundo`, lancer `claude` et effectuer la
reconnexion proposée. Redémarrer ensuite le bridge :

```bash
systemctl --user restart job-search-cli-bridge.service
```

Codex reste utilisable pendant que Claude est déconnecté.

## Garde-fous

- service lié à un socket Unix de mode `0600` ;
- jeton aléatoire non versionné ;
- une seule génération CLI à la fois ;
- Codex exécuté dans un répertoire vide, en sandbox lecture seule, sans outil,
  règle, plugin ni configuration de projet ;
- Claude exécuté sans outil, MCP, plugin, hook ni source de réglages ;
- aucune annonce, réponse IA, sortie brute des CLI ou valeur du jeton dans les journaux ;
- connexions partielles limitées par délai et nombre maximal ;
- contrôles Python du CV toujours appliqués après chaque agent ;
- modèle et niveau de raisonnement validés avant tout appel CLI ;
- échec technique ou JSON invalide suivi du secours suivant pour ce rôle.
