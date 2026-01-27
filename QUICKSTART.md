# 🚀 QUICKSTART - Démarrage Rapide

## Pour Claude Code : Étapes Essentielles

### 1. Copier les Fichiers (5 min)

Vous avez reçu ces fichiers :
```
job-search-automation-brief.md    # Brief complet
README.md                         # Documentation complète
CLAUDE_CODE_GUIDE.md              # Guide de dev pour Claude Code
requirements.txt                  # Dépendances Python
.env.example                      # Template configuration
.gitignore                        # Fichiers à ignorer
config/
  ├── criteria.yaml               # Vos critères de recherche
  └── email_template.html         # Template email
.github/workflows/
  └── daily_scrape.yml            # GitHub Actions config
```

**Action** : Créer un dossier `job-search-automation/` et y copier tous ces fichiers.

### 2. Ouvrir dans Claude Code (1 min)

```bash
# Ouvrir Claude Code dans ce dossier
cd job-search-automation
# Lancer Claude Code ou votre IDE
```

### 3. Dire à Claude Code Quoi Faire (2 min)

**Commande exacte à donner à Claude Code** :

```
Bonjour ! Je veux que tu développes ce système de recherche d'emploi automatisé.

Voici le brief complet : [coller job-search-automation-brief.md]

Consignes :
1. Lis attentivement le brief (toutes les specs sont dedans)
2. Suis l'ordre de développement dans CLAUDE_CODE_GUIDE.md
3. Commence par créer la structure complète du projet
4. Développe module par module en testant chacun
5. Priorise : Indeed scraper > Filtrage > Scoring > IA > Google Sheets > Email
6. Dis-moi quand tu es bloqué ou as besoin de clarification

Je veux un système fonctionnel qui :
- Scrape 4 sites (Indeed, APEC, WTTJ, Emploi-asso)
- Filtre selon mes critères dans config/criteria.yaml
- Analyse avec DeepSeek AI
- Stocke dans Google Sheets
- Envoie un email quotidien

Commençons !
```

### 4. Pendant le Développement

**Claude Code va probablement te demander** :

#### A. Clés API
Prépare-toi à fournir (dans `.env`) :
- [ ] `DEEPSEEK_API_KEY` - Obtenir sur https://platform.deepseek.com
- [ ] `GOOGLE_SHEETS_CREDENTIALS_JSON` - Voir section Google Cloud
- [ ] `GOOGLE_SHEET_ID` - ID de ton Google Sheet
- [ ] `EMAIL_SENDER` & `EMAIL_PASSWORD` - Compte Gmail

#### B. Google Cloud Setup
1. Créer projet : https://console.cloud.google.com
2. Activer Google Sheets API
3. Créer Service Account
4. Télécharger JSON credentials
5. Créer un Google Sheet vide
6. Partager le sheet avec l'email du service account

#### C. Gmail App Password
1. https://myaccount.google.com
2. Sécurité > Validation 2 étapes (activer)
3. Mots de passe des applications > Générer
4. Copier le mot de passe 16 caractères

### 5. Tests

**Tester chaque module** :
```bash
# Après chaque module développé
python -c "from scrapers.indeed_scraper import IndeedScraper; print('✅ Scraper OK')"
python -c "from filters.keyword_filter import filter_by_keywords; print('✅ Filtres OK')"
python -c "from analyzers.ai_analyzer import AIAnalyzer; print('✅ IA OK')"
python -c "from storage.google_sheets import GoogleSheetsStorage; print('✅ Sheets OK')"
python -c "from notifications.email_sender import EmailSender; print('✅ Email OK')"
```

**Test complet** :
```bash
python main.py
```

### 6. Déploiement GitHub Actions

Une fois que `python main.py` fonctionne localement :

```bash
# Push sur GitHub
git init
git add .
git commit -m "Job search automation system"
git remote add origin https://github.com/TON-USERNAME/job-search-automation.git
git push -u origin main

# Configurer les secrets dans GitHub
# Settings > Secrets and variables > Actions > New repository secret
# Ajouter : DEEPSEEK_API_KEY, GOOGLE_SHEETS_CREDENTIALS_JSON, 
#          GOOGLE_SHEET_ID, EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT

# Tester le workflow
# Actions > Daily Job Scraping > Run workflow
```

---

## ⚡ Checklist Minimale

- [ ] Fichiers copiés dans dossier projet
- [ ] Claude Code ouvert
- [ ] Brief donné à Claude Code
- [ ] `.env` créé avec vraies valeurs
- [ ] Google Cloud configuré (Service Account + Sheet)
- [ ] Gmail App Password généré
- [ ] DeepSeek API key obtenue et créditée
- [ ] Tests modules individuels passent
- [ ] `python main.py` fonctionne localement
- [ ] Email reçu avec offres
- [ ] Google Sheet mis à jour
- [ ] Push GitHub + Secrets configurés
- [ ] GitHub Actions test manuel réussi

---

## 🆘 Si Problème

1. **Vérifier les logs** : `data/logs/`
2. **Tester connexions** :
   ```bash
   # DeepSeek
   python -c "from openai import OpenAI; import os; client = OpenAI(api_key=os.getenv('DEEPSEEK_API_KEY'), base_url='https://api.deepseek.com'); print('✅ DeepSeek OK')"
   
   # Google Sheets
   python -c "import gspread; from google.oauth2.service_account import Credentials; import json, os; creds = Credentials.from_service_account_info(json.loads(os.getenv('GOOGLE_SHEETS_CREDENTIALS_JSON'))); client = gspread.authorize(creds); print('✅ Google Sheets OK')"
   
   # Email
   python -c "import smtplib, os; server = smtplib.SMTP('smtp.gmail.com', 587); server.starttls(); server.login(os.getenv('EMAIL_SENDER'), os.getenv('EMAIL_PASSWORD')); print('✅ Email OK')"
   ```

3. **Consulter README.md** section Troubleshooting

---

## 📞 Questions Fréquentes

**Q: Combien de temps pour développer ?**  
R: 6-8h avec Claude Code. Plus rapide qu'à la main !

**Q: Coût mensuel ?**  
R: ~2-3€/mois (DeepSeek API seulement, reste gratuit)

**Q: Fonctionne sur Windows ?**  
R: Oui, juste adapter les commandes (venv\Scripts\activate au lieu de source venv/bin/activate)

**Q: Puis-je ajouter d'autres sites ?**  
R: Oui ! Créer un nouveau scraper dans `scrapers/` et l'ajouter à `main.py`

**Q: Puis-je modifier les critères ?**  
R: Oui, éditer `config/criteria.yaml` et relancer

---

**C'est parti ! 🚀**

Donne le brief à Claude Code et laisse-le développer. Supervise juste et fournis les clés API quand demandées.
