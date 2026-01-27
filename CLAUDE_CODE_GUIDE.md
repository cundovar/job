# 🚀 Guide Rapide pour Claude Code

Ce document résume les commandes et étapes essentielles pour développer le système avec Claude Code.

---

## 📋 Ordre de Développement Recommandé

### Phase 1 : Setup Initial (30 min)
```bash
# 1. Créer la structure du projet
mkdir -p job-search-automation/{config,scrapers,filters,analyzers,storage,notifications,utils,data/logs}
cd job-search-automation

# 2. Copier les fichiers de config fournis
# - job-search-automation-brief.md
# - criteria.yaml → config/
# - .env.example
# - requirements.txt
# - README.md

# 3. Créer l'environnement virtuel
python -m venv venv
source venv/bin/activate  # Mac/Linux
# ou venv\Scripts\activate sur Windows

# 4. Installer dépendances
pip install -r requirements.txt

# 5. Créer .env depuis .env.example
cp .env.example .env
# Éditer .env avec vos vraies credentials
```

### Phase 2 : Structure de Base (1h)

#### A. Créer `utils/logger.py`
```python
"""
Système de logging centralisé avec couleurs et fichiers
"""
import logging
import colorlog
from pathlib import Path

def setup_logger(name: str, log_file: str = None) -> logging.Logger:
    # TODO: Implémenter
    pass
```

#### B. Créer `utils/rate_limiter.py`
```python
"""
Rate limiting pour respecter les sites web
"""
import time
from functools import wraps

def rate_limit(delay_seconds: int = 2):
    # TODO: Implémenter decorator
    pass
```

#### C. Créer `scrapers/base_scraper.py`
```python
"""
Classe abstraite pour tous les scrapers
"""
from abc import ABC, abstractmethod
from typing import List, Dict

class BaseScraper(ABC):
    @abstractmethod
    def scrape(self, keywords: List[str]) -> List[Dict]:
        # TODO: Définir interface
        pass
```

### Phase 3 : Scrapers (2-3h)

**Ordre recommandé** : Indeed > Emploi-asso > APEC > WTTJ

#### Indeed Scraper Template
```python
"""
scrapers/indeed_scraper.py
"""
from .base_scraper import BaseScraper
import requests
from bs4 import BeautifulSoup

class IndeedScraper(BaseScraper):
    BASE_URL = "https://fr.indeed.com/jobs"
    
    def scrape(self, keywords: List[str]) -> List[Dict]:
        """
        Scrape Indeed.fr pour les mots-clés donnés
        
        Returns:
            List[Dict]: Liste d'offres avec structure:
            {
                'title': str,
                'company': str,
                'location': str,
                'contract_type': str,
                'salary': str | None,
                'description': str,
                'url': str,
                'source': 'indeed',
                'scraped_at': datetime
            }
        """
        # TODO: Implémenter
        pass
```

**Points d'attention** :
- Utiliser BeautifulSoup pour parser HTML
- Respecter rate limiting (2 sec entre requêtes)
- Gérer timeouts et erreurs réseau
- Parser structure HTML (inspecter le site d'abord)
- Extraire toutes les infos nécessaires

#### Test Rapide
```bash
# Tester chaque scraper individuellement
python -c "
from scrapers.indeed_scraper import IndeedScraper
scraper = IndeedScraper()
jobs = scraper.scrape(['formateur web'])
print(f'Found {len(jobs)} jobs')
print(jobs[0] if jobs else 'No jobs found')
"
```

### Phase 4 : Filtrage (1h)

#### A. `filters/keyword_filter.py`
```python
"""
Filtre par mots-clés (titre, description)
"""
def filter_by_keywords(jobs: List[Dict], criteria: Dict) -> List[Dict]:
    """
    Filtre les offres selon mots-clés des critères
    Retourne uniquement les offres pertinentes
    """
    # TODO: Implémenter
    pass
```

#### B. `filters/location_filter.py`
```python
"""
Filtre géographique
"""
def filter_by_location(jobs: List[Dict], accepted_zones: List[str]) -> List[Dict]:
    # TODO: Implémenter
    pass
```

#### C. `filters/contract_filter.py`
```python
"""
Filtre type de contrat
"""
def filter_by_contract(jobs: List[Dict], accepted_contracts: List[str]) -> List[Dict]:
    # TODO: Implémenter
    pass
```

### Phase 5 : Scoring (1h)

#### `analyzers/scoring_engine.py`
```python
"""
Calcule un score 0-100 pour chaque offre
"""
def calculate_score(job: Dict, criteria: Dict) -> int:
    """
    Score basé sur :
    - Correspondance poste (40 pts)
    - Secteur (30 pts)
    - Type contrat (15 pts)
    - Localisation (10 pts)
    - Bonus (5 pts)
    
    Returns:
        int: Score 0-100
    """
    # TODO: Implémenter selon brief
    pass
```

### Phase 6 : Analyse IA (1h)

#### `analyzers/ai_analyzer.py`
```python
"""
Analyse IA avec DeepSeek
"""
from openai import OpenAI
import os
import json

class AIAnalyzer:
    def __init__(self):
        self.client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com"
        )
    
    def analyze_job(self, job: Dict, user_profile: Dict) -> Dict:
        """
        Analyse une offre avec DeepSeek
        
        Returns:
            Dict: {
                'pertinence_score': 0-10,
                'points_forts': List[str],
                'points_faibles': List[str],
                'red_flags': List[str],
                'recommandation': 'POSTULER|PEUT-ÊTRE|PASSER',
                'angle_motivation': str,
                'raison_breve': str
            }
        """
        # TODO: Implémenter selon prompt dans brief
        pass
```

### Phase 7 : Google Sheets (1h)

#### `storage/google_sheets.py`
```python
"""
Intégration Google Sheets
"""
import gspread
from google.oauth2.service_account import Credentials
import json
import os

class GoogleSheetsStorage:
    def __init__(self):
        # TODO: Setup credentials
        # TODO: Ouvrir le sheet
        pass
    
    def create_or_update_tabs(self):
        # TODO: Créer les 4 onglets si pas existants
        pass
    
    def add_jobs(self, jobs: List[Dict]):
        # TODO: Ajouter à l'onglet "Nouvelles Offres"
        pass
    
    def update_statistics(self):
        # TODO: Mettre à jour stats
        pass
```

### Phase 8 : Email (1h)

#### `notifications/email_sender.py`
```python
"""
Envoi d'emails quotidiens
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class EmailSender:
    def send_daily_report(self, jobs: List[Dict], stats: Dict):
        """
        Envoie le rapport quotidien en HTML
        Template dans config/email_template.html
        """
        # TODO: Implémenter
        pass
```

### Phase 9 : Orchestration (30 min)

#### `main.py`
```python
"""
Point d'entrée principal
"""
import yaml
from scrapers import IndeedScraper, APECScraper, WTTJScraper, EmploiAssoScraper
from filters import filter_by_keywords, filter_by_location, filter_by_contract
from analyzers import calculate_score, AIAnalyzer
from storage import GoogleSheetsStorage, JSONStorage
from notifications import EmailSender
from utils import setup_logger

def main():
    # 1. Load config
    with open('config/criteria.yaml') as f:
        criteria = yaml.safe_load(f)
    
    logger = setup_logger('main')
    logger.info("Starting job search automation...")
    
    # 2. Scrape tous les sites
    all_jobs = []
    scrapers = [
        IndeedScraper(),
        APECScraper(),
        WTTJScraper(),
        EmploiAssoScraper()
    ]
    
    for scraper in scrapers:
        try:
            jobs = scraper.scrape(criteria['keywords'])
            all_jobs.extend(jobs)
            logger.info(f"{scraper.__class__.__name__}: {len(jobs)} jobs")
        except Exception as e:
            logger.error(f"{scraper.__class__.__name__} failed: {e}")
    
    # 3. Filtrer
    filtered_jobs = filter_by_keywords(all_jobs, criteria)
    filtered_jobs = filter_by_location(filtered_jobs, criteria)
    filtered_jobs = filter_by_contract(filtered_jobs, criteria)
    
    # 4. Scorer
    for job in filtered_jobs:
        job['score'] = calculate_score(job, criteria)
    
    # 5. Analyser avec IA (seulement score >= 50)
    ai_analyzer = AIAnalyzer()
    for job in filtered_jobs:
        if job['score'] >= 50:
            job['ai_analysis'] = ai_analyzer.analyze_job(job, criteria['user_profile'])
    
    # 6. Stocker
    sheets = GoogleSheetsStorage()
    sheets.add_jobs(filtered_jobs)
    
    json_storage = JSONStorage()
    json_storage.save(filtered_jobs)
    
    # 7. Notifier
    email = EmailSender()
    top_jobs = sorted(filtered_jobs, key=lambda x: x['score'], reverse=True)[:5]
    email.send_daily_report(top_jobs, {'total': len(filtered_jobs)})
    
    logger.info(f"Done! Processed {len(filtered_jobs)} jobs")

if __name__ == "__main__":
    main()
```

---

## 🧪 Testing Strategy

### Test Chaque Module Séparément

```bash
# Test scraper
python -c "from scrapers.indeed_scraper import IndeedScraper; print(IndeedScraper().scrape(['dev web'])[:2])"

# Test filtres
python -c "from filters.keyword_filter import filter_by_keywords; ..."

# Test scoring
python -c "from analyzers.scoring_engine import calculate_score; ..."

# Test IA
python -c "from analyzers.ai_analyzer import AIAnalyzer; ..."

# Test Google Sheets
python -c "from storage.google_sheets import GoogleSheetsStorage; GoogleSheetsStorage().test_connection()"

# Test Email
python -c "from notifications.email_sender import EmailSender; EmailSender().send_test_email()"
```

### Test Complet

```bash
# Test avec dry-run (pas d'envoi email)
DRY_RUN=true python main.py

# Test réel
python main.py
```

---

## 🔍 Debug Commands

```bash
# Voir les logs en temps réel
tail -f data/logs/job_search_$(date +%Y-%m-%d).log

# Vérifier les jobs en cache
cat data/jobs_cache.json | jq '.[] | {title, company, score}'

# Test connexion DeepSeek
python -c "
from openai import OpenAI
import os
client = OpenAI(api_key=os.getenv('DEEPSEEK_API_KEY'), base_url='https://api.deepseek.com')
print(client.chat.completions.create(model='deepseek-chat', messages=[{'role':'user','content':'test'}]))
"

# Test connexion Google Sheets
python -c "
import gspread
from google.oauth2.service_account import Credentials
import json, os
creds = Credentials.from_service_account_info(json.loads(os.getenv('GOOGLE_SHEETS_CREDENTIALS_JSON')))
client = gspread.authorize(creds)
sheet = client.open_by_key(os.getenv('GOOGLE_SHEET_ID'))
print(f'Connected to: {sheet.title}')
"
```

---

## 🚨 Common Issues & Quick Fixes

### "Module not found"
```bash
pip install -r requirements.txt
```

### "Invalid API key"
```bash
# Vérifier .env
cat .env | grep DEEPSEEK
# Recharger
source .env
```

### "Permission denied" (Google Sheets)
- Vérifier que le sheet est partagé avec le service account email
- Vérifier le GOOGLE_SHEET_ID dans .env

### Rate limiting / 429 errors
```bash
# Augmenter le délai dans .env
echo "SCRAPING_DELAY_SECONDS=5" >> .env
```

---

## 📦 Git Workflow

```bash
# Setup initial
git init
git add .
git commit -m "Initial commit"

# Créer repo sur GitHub (private)
git remote add origin https://github.com/USERNAME/job-search-automation.git
git push -u origin main

# Commits réguliers
git add .
git commit -m "Add Indeed scraper"
git push

# Feature branches
git checkout -b feature/apec-scraper
# ... work ...
git commit -m "Implement APEC scraper"
git checkout main
git merge feature/apec-scraper
```

---

## ✅ Checklist Avant GitHub Actions

- [ ] Tous les scrapers fonctionnent localement
- [ ] Filtres et scoring testés
- [ ] Analyse IA fonctionne (test avec 1-2 offres)
- [ ] Google Sheets mis à jour correctement
- [ ] Email reçu avec bon format
- [ ] .env dans .gitignore
- [ ] .github/workflows/daily_scrape.yml créé
- [ ] GitHub Secrets configurés
- [ ] Test manuel du workflow réussi

---

**Bon développement avec Claude Code ! 🚀**
