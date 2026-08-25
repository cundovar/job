# 🎯 Job Search Automation System

Système automatisé de recherche d'emploi avec scraping web, analyse IA (DeepSeek), et notifications quotidiennes.

**Créé pour** : Claude Varas  
**Objectif** : Recherche d'emploi dans secteur ESS/Public/Impact (formateur dev web, chef de projet digital)

---

## 📋 Table des Matières

- [Fonctionnalités](#fonctionnalités)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Configuration](#configuration)
- [Utilisation](#utilisation)
- [Déploiement GitHub Actions](#déploiement-github-actions)
- [Maintenance](#maintenance)
- [Troubleshooting](#troubleshooting)

---

## ✨ Fonctionnalités

### Scraping Automatique
- ✅ **Indeed.fr** - Volume important d'offres
- ✅ **APEC.fr** - Offres qualifiées pour cadres
- ✅ **Welcome to the Jungle** - Startups et scale-ups
- ✅ **Emploi-asso.org** - Spécialiste ESS

### Filtrage Intelligent
- 🎯 Mots-clés personnalisés (postes, secteurs)
- 📍 Filtrage géographique (Paris + IDF + Remote)
- 📄 Type de contrat (CDI, CDD 6+, Freelance)
- 🚩 Détection automatique des red flags

### Analyse IA (DeepSeek)
- 🤖 Score de pertinence 0-10
- ✅ Points forts / Points faibles de votre candidature
- 🚨 Détection de red flags
- 💡 Recommandation : POSTULER / PEUT-ÊTRE / PASSER
- 📝 Angle d'attaque pour lettre de motivation

### Stockage & Suivi
- 📊 Google Sheets avec 4 onglets
- 📈 Statistiques et graphiques automatiques
- ✅ Suivi des candidatures
- 🔄 Mise à jour quotidienne

### Notifications
- 📧 Email quotidien à 8h
- 🌟 Top 5 opportunités du jour
- 📊 Statistiques hebdomadaires

---

## 🔧 Prérequis

### Logiciels Requis

- **Python 3.10+** : [Télécharger](https://www.python.org/downloads/)
- **Git** : [Télécharger](https://git-scm.com/downloads)
- **Compte GitHub** : [Créer](https://github.com/signup) (gratuit)

### Comptes & APIs Requis

1. **DeepSeek API** (payant, ~2-3€/mois)
   - Créer compte : https://platform.deepseek.com
   - Obtenir clé API
   - Recharger ~5€ de crédit

2. **Google Cloud** (gratuit)
   - Créer projet : https://console.cloud.google.com
   - Activer Google Sheets API
   - Créer Service Account + télécharger JSON credentials

3. **Gmail** (gratuit si vous avez déjà un compte)
   - Activer validation en 2 étapes
   - Générer mot de passe d'application

---

## 📥 Installation

### 1. Cloner le Projet

```bash
# Cloner le repo
git clone https://github.com/VOTRE-USERNAME/job-search-automation.git
cd job-search-automation

# Ou créer depuis zéro
mkdir job-search-automation
cd job-search-automation
# Copier tous les fichiers fournis ici
```

### 2. Créer un Environnement Virtuel (Recommandé)

```bash
# Créer l'environnement virtuel
python -m venv venv

# Activer l'environnement
# Sur Windows :
venv\Scripts\activate
# Sur Mac/Linux :
source venv/bin/activate
```

### 3. Installer les Dépendances

```bash
pip install -r requirements.txt
```

---

## ⚙️ Configuration

### 1. Configurer Google Sheets API

#### A. Créer un Projet Google Cloud

1. Aller sur https://console.cloud.google.com
2. Créer un nouveau projet (ex: "Job Search Automation")
3. Activer **Google Sheets API**
   - Menu APIs & Services > Bibliothèque
   - Rechercher "Google Sheets API"
   - Cliquer "Activer"

#### B. Créer un Service Account

1. Menu APIs & Services > Identifiants
2. Créer des identifiants > Compte de service
3. Nom : "job-search-bot" (ou autre)
4. Rôle : Éditeur
5. Créer la clé JSON et télécharger

#### C. Créer le Google Sheet

1. Créer un nouveau Google Sheet
2. Le nommer "Job Search Automation - Claude Varas"
3. Copier l'ID du sheet depuis l'URL
   - URL : `https://docs.google.com/spreadsheets/d/1ABC123DEF456/edit`
   - ID : `1ABC123DEF456`
4. **Important** : Partager le sheet avec l'email du service account
   - Clic droit > Partager
   - Ajouter l'email du service account (visible dans le JSON téléchargé)
   - Donner accès "Éditeur"

### 2. Configurer Gmail pour Envoi d'Emails

1. Aller sur https://myaccount.google.com
2. Sécurité > Validation en deux étapes (activer si pas déjà fait)
3. Sécurité > Mots de passe des applications
4. Générer un nouveau mot de passe d'application
   - Application : "Autre (nom personnalisé)"
   - Nom : "Job Search Bot"
   - Copier le mot de passe 16 caractères généré

### 3. Créer le Fichier .env

```bash
# Copier le template
cp .env.example .env

# Éditer avec votre éditeur préféré
nano .env
# ou
code .env
```

**Remplir les valeurs** :

```bash
# DeepSeek API
DEEPSEEK_API_KEY=sk-VOTRE-CLE-ICI

# Google Sheets (coller TOUT le JSON sur une ligne)
GOOGLE_SHEETS_CREDENTIALS_JSON={"type":"service_account",...TOUT_LE_JSON...}
GOOGLE_SHEET_ID=VOTRE-SHEET-ID-ICI

# Email
EMAIL_SENDER=votre-email@gmail.com
EMAIL_PASSWORD=votre-mot-de-passe-16-caracteres
EMAIL_RECIPIENT=varas.cundo@gmail.com
```

### 4. Personnaliser les Critères (Optionnel)

Éditer `config/criteria.yaml` pour ajuster :
- Mots-clés de recherche
- Secteurs prioritaires
- Red flags
- Seuils de scoring

---

## 🚀 Utilisation

### Lancement Manuel

```bash
# Activer l'environnement virtuel (si pas déjà fait)
source venv/bin/activate  # Mac/Linux
# ou
venv\Scripts\activate  # Windows

# Lancer le script
python main.py
```

**Ce qui se passe** :
1. ✅ Scrape les 4 sites d'emploi
2. ✅ Filtre selon vos critères
3. ✅ Analyse avec DeepSeek AI
4. ✅ Met à jour Google Sheet
5. ✅ Envoie email avec résumé

### Commandes Hermes

Les commandes utilisables par Hermes sont documentees ici :

```text
docs/HERMES_COMMANDS.md
```

Commandes principales :

```bash
python3 -m hermes_commands.job_top
python3 -m hermes_commands.job_today
python3 -m hermes_commands.job_prepare 1
python3 -m hermes_commands.job_apply 1
python3 -m hermes_commands.job_relance
python3 -m hermes_commands.job_status
```

### CV personnalisé et version ATS

La génération produit deux présentations du même contenu vérifié :

- `cv_ats.pdf`, sobre et mono-colonne, pour les formulaires de candidature ;
- `cv_final.pdf`, avec la mise en page design, pour un envoi direct ou une lecture humaine.

Elle expose séparément l'éligibilité, le parsing, la correspondance, la qualité humaine et la véracité. Les scores sont des indicateurs internes et ne reproduisent pas une note secrète d'un ATS. Voir [docs/CV_ASSESSMENT.md](docs/CV_ASSESSMENT.md).

Les sorties Markdown et Canva ne sont plus générées.

### Agents IA par abonnement sur Netcup

Sur le déploiement Coolify, l'analyse des annonces et la création des CV utilisent
en priorité Codex CLI, puis Claude Code, via un socket Unix privé partagé avec le
VPS. Les clés DeepSeek et Anthropic deviennent des replis facultatifs.

Installation, sécurité et diagnostic : [docs/CV_CLI_BRIDGE.md](docs/CV_CLI_BRIDGE.md).

**Durée** : 5-10 minutes selon le nombre d'offres

### Vérifier les Résultats

1. **Email** : Vérifier votre boîte mail (varas.cundo@gmail.com)
2. **Google Sheet** : Ouvrir le sheet partagé
   - Onglet "Nouvelles Offres" : Toutes les nouvelles découvertes
   - Onglet "À Postuler" : Vos sélections
   - Onglet "Statistiques" : Graphiques

3. **Logs** : Consulter `data/logs/` pour détails

---

## 🤖 Déploiement GitHub Actions

Pour automatiser l'exécution quotidienne à 8h :

### 1. Créer un Repo GitHub

```bash
# Initialiser Git (si pas déjà fait)
git init
git add .
git commit -m "Initial commit: Job search automation"

# Créer repo sur GitHub
# Aller sur github.com > New Repository
# Nom : job-search-automation
# Visibilité : Private (recommandé)

# Lier le repo local
git remote add origin https://github.com/VOTRE-USERNAME/job-search-automation.git
git branch -M main
git push -u origin main
```

### 2. Configurer les Secrets GitHub

1. Sur GitHub, aller dans votre repo
2. Settings > Secrets and variables > Actions
3. Cliquer "New repository secret"
4. Ajouter chaque secret :

| Nom | Valeur |
|-----|--------|
| `DEEPSEEK_API_KEY` | Votre clé DeepSeek |
| `GOOGLE_SHEETS_CREDENTIALS_JSON` | Tout le JSON (sur une ligne) |
| `GOOGLE_SHEET_ID` | ID de votre sheet |
| `EMAIL_SENDER` | Votre email Gmail |
| `EMAIL_PASSWORD` | Mot de passe application 16 car |
| `EMAIL_RECIPIENT` | varas.cundo@gmail.com |

### 3. Activer GitHub Actions

1. Aller dans l'onglet "Actions" du repo
2. Activer les workflows
3. Le workflow `.github/workflows/daily_scrape.yml` sera actif

### 4. Tester le Workflow

```bash
# Aller dans Actions > Daily Job Scraping
# Cliquer "Run workflow" > "Run workflow"
# Suivre l'exécution en temps réel
```

**C'est tout !** 🎉

Le système tournera automatiquement tous les jours à 8h (heure de Paris).

---

## 🔧 Maintenance

### Mettre à Jour les Critères

1. Éditer `config/criteria.yaml` localement
2. Commit et push :
   ```bash
   git add config/criteria.yaml
   git commit -m "Update search criteria"
   git push
   ```
3. Changement pris en compte dès la prochaine exécution

### Vérifier les Logs

**Localement** :
```bash
tail -f data/logs/job_search_YYYY-MM-DD.log
```

**Sur GitHub Actions** :
- Actions > Dernière exécution > Voir les logs

### Gérer les Erreurs de Scraping

Si un site bloque le scraping :
1. Vérifier `data/logs/` pour l'erreur exacte
2. Le système continue avec les autres sites
3. Si besoin, désactiver temporairement le site dans `config/criteria.yaml`

---

## 🐛 Troubleshooting

### Erreur : "Invalid API Key" (DeepSeek)

**Solution** :
- Vérifier que la clé est correcte dans `.env`
- Vérifier le crédit sur platform.deepseek.com
- Recharger si solde épuisé

### Erreur : "Permission denied" (Google Sheets)

**Solution** :
- Vérifier que le sheet est partagé avec l'email du service account
- Vérifier que le service account a accès "Éditeur"
- Vérifier que l'ID du sheet est correct

### Erreur : "Authentication failed" (Gmail)

**Solution** :
- Vérifier que la validation en 2 étapes est activée
- Régénérer un mot de passe d'application
- Vérifier que c'est bien le mot de passe 16 car (pas votre mot de passe Gmail principal)

### Pas d'email reçu

**Vérifications** :
1. Vérifier spam/promotions
2. Vérifier les logs : `data/logs/`
3. Tester l'envoi manuellement :
   ```bash
   python -c "from notifications.email_sender import EmailSender; EmailSender().send_test_email()"
   ```

### Sites de Scraping Bloquent

**Solutions** :
1. Augmenter le délai entre requêtes dans `.env` :
   ```
   SCRAPING_DELAY_SECONDS=5
   ```
2. Utiliser un VPN si nécessaire
3. Désactiver temporairement le site problématique

### GitHub Actions Ne Se Lance Pas

**Vérifications** :
1. Actions activées dans Settings > Actions
2. Fichier `.github/workflows/daily_scrape.yml` présent
3. Secrets bien configurés
4. Workflow activé (peut être désactivé par défaut)

---

## 📊 Statistiques & Métriques

Le système track automatiquement :
- Nombre d'offres scrapées par jour
- Taux de filtrage (% offres pertinentes)
- Répartition par secteur
- Taux de réponse aux candidatures

Consultez l'onglet "Statistiques" du Google Sheet.

---

## 🔒 Sécurité & Confidentialité

- ⚠️ **Ne JAMAIS commit le fichier `.env`** dans Git
- ✅ `.env` est dans `.gitignore`
- ✅ Utiliser GitHub Secrets pour les credentials
- ✅ Repo privé recommandé
- ✅ Rotation régulière des API keys

---

## 📞 Support

**Créateur** : Claude (AI Assistant)  
**Utilisateur** : Claude Varas  
**Email** : varas.cundo@gmail.com

Pour questions techniques, créer une issue sur GitHub ou contacter le développeur.

---

## 📝 Changelog

### Version 1.0 (Janvier 2026)
- ✅ Scraping Indeed, APEC, WTTJ, Emploi-asso
- ✅ Filtrage intelligent multi-critères
- ✅ Analyse IA avec DeepSeek
- ✅ Intégration Google Sheets
- ✅ Emails quotidiens
- ✅ Déploiement GitHub Actions

---

## 🚀 Roadmap (Améliorations Futures)

- [ ] Interface web pour consulter les offres
- [ ] Machine Learning pour améliorer le scoring
- [ ] Intégration LinkedIn
- [ ] Auto-application sur certains sites
- [ ] Alertes temps réel pour offres très pertinentes
- [ ] Support multi-utilisateurs

---

## 📄 Licence

Usage personnel uniquement. Code fourni tel quel sans garantie.

---

**Bonne recherche d'emploi ! 🎯**
