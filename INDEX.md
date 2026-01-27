# 📦 INDEX - Contenu du Package

## 📄 Fichiers Principaux

### 🚀 QUICKSTART.md (COMMENCEZ ICI !)
**C'est par ici !** Guide de démarrage rapide avec les étapes essentielles.
- Étapes minimales pour démarrer
- Commandes exactes à donner à Claude Code
- Checklist complète
- Durée : 10 minutes de lecture

### 📋 job-search-automation-brief.md
Brief technique complet pour Claude Code avec :
- Objectif du projet
- Votre profil utilisateur détaillé
- Critères de recherche complets
- Architecture technique recommandée
- Spécifications de chaque module
- Exemples de code
- Durée : À donner à Claude Code, pas besoin de tout lire

### 👨‍💻 CLAUDE_CODE_GUIDE.md
Guide de développement pour Claude Code :
- Ordre de développement module par module
- Templates de code pour chaque composant
- Commandes de test
- Debug tips
- Git workflow
- Durée : Référence pendant le développement

### 📖 README.md
Documentation complète du projet :
- Installation détaillée
- Configuration pas à pas
- Guide d'utilisation
- Déploiement GitHub Actions
- Troubleshooting
- Durée : Référence une fois le projet développé

---

## ⚙️ Fichiers de Configuration

### 📝 config/criteria.yaml
**VOS critères de recherche personnalisés**
- Postes recherchés (formateur, chef de projet, dev...)
- Secteurs acceptés (ESS, public, impact)
- Localisation (Paris + IDF + Remote)
- Types de contrat (CDI, CDD 6+, freelance)
- Red flags à exclure
- Scoring weights

**Action** : Vérifier et ajuster si besoin avant de lancer

### 🔐 .env.example
Template des variables d'environnement à remplir :
- DeepSeek API key
- Google Sheets credentials
- Email configuration
- Paramètres optionnels

**Action** : Copier vers `.env` et remplir avec vos vraies valeurs

### 📧 config/email_template.html
Template HTML pour les emails quotidiens.
Design professionnel avec :
- En-tête moderne
- Statistiques visuelles
- Cartes d'offres avec couleurs
- Recommandations IA
- Footer avec liens

**Action** : Peut être personnalisé si vous voulez un style différent

---

## 🔧 Fichiers Techniques

### 📦 requirements.txt
Liste des dépendances Python nécessaires :
- requests, beautifulsoup4 (scraping)
- openai (DeepSeek API)
- gspread, google-auth (Google Sheets)
- pandas, pyyaml (data processing)
- etc.

**Action** : `pip install -r requirements.txt`

### 🚫 .gitignore
Fichiers à ne jamais commit sur Git :
- `.env` (secrets !)
- `venv/` (environnement virtuel)
- `data/` (logs et cache)
- `*.pyc` (fichiers compilés)
- Credentials JSON

**Action** : Essentiel pour la sécurité, ne pas modifier

### 🤖 .github/workflows/daily_scrape.yml
Configuration GitHub Actions pour automatisation :
- Exécution quotidienne à 8h (heure Paris)
- Installation dépendances
- Exécution du script
- Upload des logs
- Notification en cas d'erreur

**Action** : Fonctionne automatiquement une fois push sur GitHub

---

## 📁 Structure Complète du Package

```
job-search-automation-package/
│
├── 🚀 QUICKSTART.md                    👈 COMMENCEZ ICI
├── 📋 job-search-automation-brief.md   👈 Donner à Claude Code
├── 👨‍💻 CLAUDE_CODE_GUIDE.md
├── 📖 README.md
│
├── ⚙️ Configuration
│   ├── .env.example                    👈 Copier vers .env
│   ├── .gitignore
│   └── config/
│       ├── criteria.yaml               👈 Vos critères
│       └── email_template.html
│
├── 🔧 Dépendances
│   └── requirements.txt                👈 pip install -r requirements.txt
│
└── 🤖 Automatisation
    └── .github/workflows/
        └── daily_scrape.yml

```

---

## 🎯 Ordre d'Utilisation Recommandé

### 1️⃣ Lecture Rapide (10 min)
- ✅ Lire `QUICKSTART.md` en entier

### 2️⃣ Setup Environnement (15 min)
- ✅ Créer dossier projet
- ✅ Copier tous les fichiers dedans
- ✅ Créer `.env` depuis `.env.example`
- ✅ Obtenir les clés API nécessaires

### 3️⃣ Développement avec Claude Code (6-8h)
- ✅ Ouvrir Claude Code dans le dossier
- ✅ Donner `job-search-automation-brief.md` à Claude Code
- ✅ Suivre le développement
- ✅ Consulter `CLAUDE_CODE_GUIDE.md` si besoin

### 4️⃣ Tests & Déploiement (1h)
- ✅ Tester localement : `python main.py`
- ✅ Vérifier email reçu + Google Sheet
- ✅ Push sur GitHub
- ✅ Configurer GitHub Secrets
- ✅ Tester GitHub Actions

### 5️⃣ Maintenance (selon besoin)
- ✅ Consulter `README.md` pour troubleshooting
- ✅ Ajuster `config/criteria.yaml` si besoin
- ✅ Surveiller les logs dans `data/logs/`

---

## 💡 Conseils Importants

### ⚠️ Sécurité
- **JAMAIS** commit le fichier `.env` sur Git
- **TOUJOURS** utiliser GitHub Secrets pour les credentials
- Garder le repo **privé** sur GitHub

### 🔑 Clés API Nécessaires
Préparez ces comptes AVANT de commencer :
1. **DeepSeek** : https://platform.deepseek.com (~5€ de crédit initial)
2. **Google Cloud** : https://console.cloud.google.com (gratuit)
3. **Gmail** : Mot de passe application (gratuit si compte existant)

### 📊 Coût Mensuel Estimé
- DeepSeek API : ~2-3€/mois
- Google Sheets : Gratuit
- GitHub Actions : Gratuit (< 2000 min/mois)
- Gmail SMTP : Gratuit
- **Total : ~2-3€/mois**

### ⏱️ Temps Estimé
- Lecture documentation : 30 min
- Setup APIs & comptes : 30 min
- Développement (Claude Code) : 6-8h
- Tests et déploiement : 1h
- **Total première installation : ~8-10h**

Ensuite, le système tourne automatiquement tous les jours sans intervention.

---

## 🆘 Aide

### Questions Pendant Setup ?
1. Consulter `QUICKSTART.md` section "Si Problème"
2. Consulter `README.md` section "Troubleshooting"
3. Vérifier les logs : `data/logs/`

### Questions Pendant Développement ?
1. Consulter `CLAUDE_CODE_GUIDE.md`
2. Demander à Claude Code de debugger
3. Tester chaque module individuellement

### Questions Après Déploiement ?
1. Consulter `README.md`
2. Vérifier GitHub Actions logs
3. Vérifier email de notification d'erreur

---

## ✅ Validation du Package

Vérifiez que vous avez bien tous ces fichiers :

- [ ] QUICKSTART.md
- [ ] job-search-automation-brief.md
- [ ] CLAUDE_CODE_GUIDE.md
- [ ] README.md
- [ ] requirements.txt
- [ ] .env.example
- [ ] .gitignore
- [ ] config/criteria.yaml
- [ ] config/email_template.html
- [ ] .github/workflows/daily_scrape.yml

**Si tous présents → Vous êtes prêt à démarrer ! 🚀**

Commencez par lire `QUICKSTART.md` !

---

**Créé pour** : Claude Varas  
**Date** : Janvier 2026  
**Objectif** : Automatiser la recherche d'emploi (formateur dev web / chef de projet digital / dev ESS)
