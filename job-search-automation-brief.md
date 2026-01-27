# Brief Technique : Système de Recherche d'Emploi Automatisé

## 🎯 Objectif du Projet

Créer un système automatisé de recherche d'emploi qui :
1. Scrape quotidiennement 4-6 sites d'emploi
2. Filtre les offres selon des critères précis
3. Analyse chaque offre avec DeepSeek AI
4. Stocke les résultats dans Google Sheets
5. Envoie un email quotidien avec les meilleures opportunités

**Budget temps estimé** : 6-8h de développement

---

## 👤 Profil Utilisateur

**Nom** : Claude Varas  
**Expérience** :
- Formateur développement web (1 an) au Pôle S (insertion)
- Stack : HTML/CSS/JS/PHP/Symfony/React/Vue.js
- BAC+2 + bootcamp 2020
- Actuellement en CDI jusqu'en mars 2026

**Situation** :
- Layoff économique prévu mars 2026 avec 12 mois maintien salarial
- Recherche active d'opportunités pour après mars 2026
- Préférence forte pour missions à impact social

---

## 🎯 Critères de Recherche

### Postes Recherchés (par ordre de priorité)

1. **Formateur développement web** (priorité absolue)
   - Mots-clés : "formateur web", "formateur développement", "enseignant développement web", "professeur web", "intervenant web"
   
2. **Chef de projet digital/web**
   - Mots-clés : "chef de projet digital", "chef de projet web", "chef de projet numérique", "responsable projet digital"
   
3. **Développeur web (secteur ESS uniquement)**
   - Mots-clés : "développeur web", "développeur fullstack", "développeur symfony", "développeur react"
   
4. **Responsable formation digitale**
   - Mots-clés : "responsable formation digitale", "coordinateur pédagogique", "coordinateur numérique", "support utilisateur"

### Secteurs Acceptés

**Priorité 1 - ESS (Économie Sociale et Solidaire)** :
- Associations loi 1901
- Fondations
- Coopératives
- Entreprises adaptées
- ESAT
- Structures d'insertion

**Priorité 2 - Secteur Public** :
- Collectivités territoriales
- Établissements publics
- Universités
- Hôpitaux publics
- Ministères

**Priorité 3 - Startups à Impact** :
- B-Corp certifiées
- Entreprises à mission
- Structures à impact social/environnemental
- EdTech à vocation sociale

**Mots-clés secteur à détecter** :
- ESS, "économie sociale et solidaire"
- Association, fondation, coopérative
- Impact social, insertion professionnelle
- Secteur public, collectivité, mairie
- B-Corp, entreprise à mission
- Culture, science, éducation

### Localisation

- **Zone géographique** : Paris + Île-de-France
- **Remote** : Acceptable (100% remote ou hybride)
- **Distance transport** : Pas de limite stricte si bonne desserte transport (utilisateur habite Pantin, 93)

### Types de Contrat

**Acceptés** :
- ✅ CDI (priorité absolue)
- ✅ CDD 6+ mois
- ✅ Freelance/Vacataire SI volume horaire garanti (minimum 15h/semaine)

**Exclus** :
- ❌ Stage
- ❌ Alternance / Apprentissage
- ❌ Bénévolat
- ❌ CDD < 6 mois
- ❌ Vacataire sans volume garanti

### Red Flags (Exclusions Automatiques)

**Mots-clés à exclure** :
- "stage", "stagiaire"
- "alternance", "apprentissage", "contrat pro"
- "bénévole", "bénévolat"
- "crypto", "cryptocurrency", "blockchain" (sauf si projet social clair)
- "web3", "NFT", "token"
- "CAC40" (grandes entreprises commerciales pures)

**Secteurs à exclure** :
- Banque/Finance commerciale (sauf banques éthiques type Crédit Coopératif, NEF)
- Assurance commerciale
- Grande distribution
- Industrie du luxe
- Gaming/Paris sportifs
- Publicité pure

### Salaire

- **Pas de filtre strict** sur le salaire pour l'instant
- L'analyse IA doit mentionner le salaire quand indiqué
- Utilisateur évaluera au cas par cas

---

## 🏗️ Architecture Technique

### Stack Recommandée

**Backend** :
- Python 3.10+
- `requests` pour les requêtes HTTP
- `beautifulsoup4` pour le parsing HTML
- `selenium` pour sites dynamiques (si nécessaire)
- `python-dotenv` pour les variables d'environnement

**AI Analysis** :
- DeepSeek API (compatible OpenAI SDK)
- Modèle : `deepseek-chat` ou `deepseek-coder`
- Coût : ~$0.27/M tokens input, ~$1.10/M tokens output

**Storage** :
- Google Sheets API (`gspread`, `google-auth`)
- JSON local pour cache/backup

**Notifications** :
- SMTP (Gmail) pour emails quotidiens
- HTML emails avec template

**Automation** :
- GitHub Actions (cron quotidien)
- Alternative : cron local si préféré

### Structure du Projet

```
job-search-automation/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
│
├── config/
│   ├── criteria.yaml          # Critères de recherche
│   └── email_template.html    # Template email
│
├── scrapers/
│   ├── __init__.py
│   ├── base_scraper.py        # Classe abstraite
│   ├── indeed_scraper.py
│   ├── apec_scraper.py
│   ├── wttj_scraper.py        # Welcome to the Jungle
│   └── emploi_asso_scraper.py
│
├── filters/
│   ├── __init__.py
│   ├── keyword_filter.py      # Filtrage mots-clés
│   ├── location_filter.py     # Filtrage géo
│   ├── sector_filter.py       # Filtrage secteur
│   └── contract_filter.py     # Filtrage type contrat
│
├── analyzers/
│   ├── __init__.py
│   ├── scoring_engine.py      # Score 0-100
│   └── ai_analyzer.py         # Analyse DeepSeek
│
├── storage/
│   ├── __init__.py
│   ├── google_sheets.py
│   └── json_storage.py
│
├── notifications/
│   ├── __init__.py
│   └── email_sender.py
│
├── utils/
│   ├── __init__.py
│   ├── logger.py
│   └── rate_limiter.py
│
├── data/                       # Créé automatiquement
│   ├── jobs_cache.json
│   └── logs/
│
├── main.py                     # Point d'entrée
│
└── .github/
    └── workflows/
        └── daily_scrape.yml    # GitHub Actions config
```

---

## 🔍 Sites à Scraper

### 1. Indeed.fr
- **Priorité** : Haute
- **Difficulté** : Moyenne
- **URL** : `https://fr.indeed.com/jobs?q={query}&l=Île-de-France`
- **Méthode** : BeautifulSoup (pas d'API officielle)
- **Rate limiting** : 1 req/2 secondes
- **Extraction** :
  - Titre poste
  - Entreprise
  - Localisation
  - Type contrat
  - Salaire (si disponible)
  - Description
  - Lien offre

### 2. APEC.fr
- **Priorité** : Haute (qualité des offres)
- **Difficulté** : Moyenne
- **URL** : `https://www.apec.fr/candidat/recherche-emploi.html/emploi?motsCles={query}`
- **Méthode** : BeautifulSoup + requests
- **Rate limiting** : 1 req/3 secondes
- **Note** : Offres souvent mieux qualifiées, secteur ESS bien représenté

### 3. Welcome to the Jungle
- **Priorité** : Moyenne
- **Difficulté** : Faible (API disponible)
- **URL API** : `https://www.welcometothejungle.com/api/graphql`
- **Méthode** : GraphQL API
- **Rate limiting** : Respecter les limites API
- **Note** : Bon pour startups à impact

### 4. Emploi-asso.org
- **Priorité** : Très haute (spécialiste ESS)
- **Difficulté** : Faible
- **URL** : `https://www.emploi-asso.org/recherche?q={query}&location=Île-de-France`
- **Méthode** : BeautifulSoup
- **Note** : Site spécialisé ESS, très pertinent pour l'utilisateur

### 5. Pôle Emploi / France Travail (optionnel)
- **Priorité** : Basse (beaucoup de bruit)
- **Difficulté** : Moyenne
- **API** : Oui (API officielle disponible)
- **Note** : À implémenter seulement si temps disponible

### 6. LinkedIn (optionnel, complexe)
- **Priorité** : Moyenne
- **Difficulté** : Très haute (anti-scraping fort)
- **Méthode** : Selenium + proxy ou API payante
- **Note** : À implémenter en dernier si possible

---

## 🤖 Système de Filtrage et Scoring

### Phase 1 : Filtrage Basique (élimine 70-80% des offres)

**Filtres obligatoires** :
1. **Mots-clés titre/description** : doit contenir au moins 1 mot-clé des postes recherchés
2. **Localisation** : Paris ou Île-de-France ou Remote
3. **Type contrat** : CDI, CDD 6+, ou Freelance avec volume
4. **Red flags** : aucun mot-clé d'exclusion

### Phase 2 : Scoring (score 0-100)

**Calcul du score** :

```python
score = 0

# Correspondance poste (40 points max)
if "formateur" in title.lower():
    score += 40
elif "chef de projet" in title.lower():
    score += 35
elif "responsable formation" in title.lower():
    score += 35
elif "développeur" in title.lower() and secteur_ess:
    score += 30

# Correspondance secteur (30 points max)
if secteur == "ESS":
    score += 30
elif secteur == "Public":
    score += 25
elif secteur == "Startup Impact":
    score += 20

# Type contrat (15 points max)
if contrat == "CDI":
    score += 15
elif contrat == "CDD 6+":
    score += 10
elif contrat == "Freelance volume garanti":
    score += 10

# Localisation (10 points max)
if location == "Paris" or "Pantin" in location:
    score += 10
elif "Île-de-France" in location:
    score += 8
elif "Remote" in location:
    score += 10

# Salaire mentionné (5 points bonus)
if salaire_indiqué:
    score += 5
```

**Seuils de décision** :
- Score < 50 : Ignoré (pas d'analyse IA)
- Score 50-70 : Analyse IA basique
- Score > 70 : Analyse IA détaillée + lettre motivation

### Phase 3 : Analyse IA (DeepSeek)

**Pour chaque offre avec score ≥ 50**, envoyer à DeepSeek :

**Prompt système** :
```
Tu es un conseiller en recherche d'emploi spécialisé dans le secteur du numérique et de l'ESS.
Ton rôle est d'analyser des offres d'emploi et de déterminer si elles correspondent au profil suivant :

PROFIL CANDIDAT :
- Formateur développement web (1 an d'expérience)
- Stack : HTML/CSS/JS/PHP/Symfony/React/Vue.js
- BAC+2 + bootcamp 2020
- Recherche CDI dans secteur ESS/Public/Impact
- Priorité : postes formateur ou chef de projet digital

ANALYSE REQUISE :
1. Pertinence globale (0-10)
2. Points forts de la candidature pour ce poste
3. Points faibles / écarts avec le profil
4. Red flags détectés
5. Recommandation : POSTULER / PEUT-ÊTRE / PASSER
6. Angle d'attaque pour la lettre de motivation (si POSTULER)
```

**Prompt utilisateur** :
```
Analyse cette offre d'emploi :

TITRE : {titre}
ENTREPRISE : {entreprise}
SECTEUR : {secteur}
LOCALISATION : {localisation}
TYPE CONTRAT : {type_contrat}
SALAIRE : {salaire si disponible}

DESCRIPTION :
{description complète}

Fournis ton analyse au format JSON :
{
  "pertinence_score": 0-10,
  "points_forts": ["point1", "point2", ...],
  "points_faibles": ["point1", "point2", ...],
  "red_flags": ["flag1", "flag2", ...],
  "recommandation": "POSTULER|PEUT-ÊTRE|PASSER",
  "angle_motivation": "Explication de comment pitcher sa candidature",
  "raison_breve": "Résumé en 1 phrase"
}
```

---

## 📊 Google Sheets Structure

### Onglet 1 : "Nouvelles Offres" (7 derniers jours)

| Colonne | Type | Description |
|---------|------|-------------|
| Date découverte | Date | Date de scraping |
| Score | Number | Score 0-100 |
| Recommandation | Text | POSTULER / PEUT-ÊTRE / PASSER |
| Titre | Text | Titre du poste |
| Entreprise | Text | Nom entreprise |
| Secteur | Text | ESS / Public / Startup / Autre |
| Localisation | Text | Ville ou Remote |
| Type contrat | Text | CDI / CDD / Freelance |
| Salaire | Text | Si indiqué |
| Pertinence IA | Number | Score 0-10 de DeepSeek |
| Points forts | Text | Résumé |
| Points faibles | Text | Résumé |
| Red flags | Text | Si détectés |
| Angle motivation | Text | Conseil DeepSeek |
| Lien offre | URL | Lien cliquable |
| Statut | Dropdown | NOUVEAU / LU / À POSTULER / POSTULÉ / REJETÉ |

**Format conditionnel** :
- Vert : Recommandation = POSTULER
- Orange : Recommandation = PEUT-ÊTRE
- Gris : Recommandation = PASSER
- Rouge : Red flags détectés

### Onglet 2 : "À Postuler" (suivi candidatures)

Filtre automatique des offres marquées "À POSTULER".

Colonnes supplémentaires :
- Date candidature envoyée
- Date relance 1
- Date relance 2
- Réponse reçue (Oui/Non)
- Type réponse (Entretien / Refus / Autre)
- Notes

### Onglet 3 : "Statistiques"

Graphiques auto-générés :
- Nombre d'offres par jour
- Répartition par secteur
- Répartition par type de poste
- Taux de recommandation IA
- Taux de réponse candidatures

### Onglet 4 : "Configuration"

Interface pour ajuster les critères :
- Mots-clés à ajouter/retirer
- Red flags personnalisés
- Seuil de score minimum
- Emails de notification

---

## 📧 Email Quotidien

**Envoi** : Tous les jours à 8h00 (heure Paris)  
**Destinataire** : varas.cundo@gmail.com

### Structure Email (HTML)

```html
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; }
        .header { background: #2c3e50; color: white; padding: 20px; }
        .summary { background: #ecf0f1; padding: 15px; margin: 20px 0; }
        .job-card { border: 1px solid #ddd; padding: 15px; margin: 10px 0; }
        .postuler { background: #27ae60; color: white; }
        .peut-etre { background: #f39c12; color: white; }
        .button { padding: 10px 20px; background: #3498db; color: white; text-decoration: none; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🎯 Votre Rapport Quotidien - {date}</h1>
    </div>
    
    <div class="summary">
        <h2>📊 Résumé</h2>
        <p><strong>{nb_nouvelles} nouvelles offres</strong> trouvées aujourd'hui</p>
        <p>
            ✅ {nb_postuler} à postuler | 
            ⚠️ {nb_peut_etre} peut-être | 
            ❌ {nb_passer} à passer
        </p>
    </div>
    
    <h2>🌟 Top 5 Opportunités</h2>
    
    <!-- Pour chaque offre dans top 5 -->
    <div class="job-card postuler">
        <h3>{titre}</h3>
        <p><strong>{entreprise}</strong> - {localisation} - {type_contrat}</p>
        <p><strong>Secteur :</strong> {secteur}</p>
        <p><strong>Score :</strong> {score}/100 | <strong>IA :</strong> {pertinence_ia}/10</p>
        
        <p><strong>✅ Points forts :</strong></p>
        <ul>
            <li>{point_fort_1}</li>
            <li>{point_fort_2}</li>
        </ul>
        
        <p><strong>💡 Angle motivation :</strong> {angle_motivation}</p>
        
        <a href="{lien_offre}" class="button">Voir l'offre</a>
    </div>
    
    <hr>
    
    <p>📊 <a href="{lien_google_sheet}">Voir toutes les offres dans Google Sheets</a></p>
    
    <p style="color: #7f8c8d; font-size: 12px;">
        Ce rapport est généré automatiquement. Pour modifier vos critères de recherche, 
        éditez l'onglet "Configuration" dans Google Sheets.
    </p>
</body>
</html>
```

---

## ⚙️ Configuration & Secrets

### Variables d'Environnement (.env)

```bash
# DeepSeek API
DEEPSEEK_API_KEY=sk-...

# Google Sheets
GOOGLE_SHEETS_CREDENTIALS_JSON={"type": "service_account", ...}
GOOGLE_SHEET_ID=1ABC...

# Email (Gmail)
EMAIL_SENDER=votre-email@gmail.com
EMAIL_PASSWORD=app-specific-password
EMAIL_RECIPIENT=varas.cundo@gmail.com

# Optional
SCRAPING_DELAY_SECONDS=2
MAX_JOBS_PER_SITE=50
SCORE_THRESHOLD_AI_ANALYSIS=50
```

### Google Cloud Setup (pour Sheets API)

1. Créer un projet Google Cloud
2. Activer Google Sheets API
3. Créer un Service Account
4. Télécharger le JSON credentials
5. Partager le Google Sheet avec l'email du service account

---

## 🚀 GitHub Actions Configuration

### Fichier `.github/workflows/daily_scrape.yml`

```yaml
name: Daily Job Scraping

on:
  schedule:
    # Tous les jours à 7h00 UTC (8h Paris hiver, 9h Paris été)
    - cron: '0 7 * * *'
  workflow_dispatch: # Permet lancement manuel

jobs:
  scrape-and-analyze:
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout repository
      uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'
    
    - name: Cache Python dependencies
      uses: actions/cache@v3
      with:
        path: ~/.cache/pip
        key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements.txt') }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
    
    - name: Run job scraper
      env:
        DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
        GOOGLE_SHEETS_CREDENTIALS_JSON: ${{ secrets.GOOGLE_SHEETS_CREDENTIALS_JSON }}
        GOOGLE_SHEET_ID: ${{ secrets.GOOGLE_SHEET_ID }}
        EMAIL_SENDER: ${{ secrets.EMAIL_SENDER }}
        EMAIL_PASSWORD: ${{ secrets.EMAIL_PASSWORD }}
        EMAIL_RECIPIENT: ${{ secrets.EMAIL_RECIPIENT }}
      run: |
        python main.py
    
    - name: Upload logs
      if: always()
      uses: actions/upload-artifact@v3
      with:
        name: scraping-logs
        path: data/logs/
```

---

## 📋 Checklist de Développement

### Phase 1 : Setup de Base (1-2h)
- [ ] Créer structure du projet
- [ ] Configurer requirements.txt
- [ ] Créer .env.example
- [ ] Setup logging basique
- [ ] Créer README.md initial

### Phase 2 : Scrapers (2-3h)
- [ ] Implémenter base_scraper.py (classe abstraite)
- [ ] Scraper Indeed
- [ ] Scraper APEC
- [ ] Scraper Welcome to the Jungle
- [ ] Scraper Emploi-asso
- [ ] Tests unitaires pour chaque scraper
- [ ] Gestion des erreurs et timeouts

### Phase 3 : Système de Filtrage (1-2h)
- [ ] Filtres par mots-clés
- [ ] Filtres géographiques
- [ ] Filtres secteur
- [ ] Filtres type contrat
- [ ] Détection red flags
- [ ] Calcul score 0-100

### Phase 4 : Analyse IA (1h)
- [ ] Intégration DeepSeek API
- [ ] Prompt engineering
- [ ] Parsing réponse JSON
- [ ] Gestion des erreurs API
- [ ] Cache pour éviter analyses dupliquées

### Phase 5 : Storage (1h)
- [ ] Intégration Google Sheets API
- [ ] Création automatique des onglets
- [ ] Mise à jour des données
- [ ] Format conditionnel
- [ ] Backup JSON local

### Phase 6 : Notifications (1h)
- [ ] Template HTML email
- [ ] Envoi via SMTP Gmail
- [ ] Gestion des pièces jointes (optionnel)
- [ ] Tests emails

### Phase 7 : Orchestration (30min)
- [ ] main.py point d'entrée
- [ ] Gestion du flow complet
- [ ] Logging détaillé
- [ ] Gestion cache pour éviter doublons

### Phase 8 : Déploiement (30min)
- [ ] Configuration GitHub Actions
- [ ] Setup secrets GitHub
- [ ] Test workflow manuel
- [ ] Vérification cron automatique

### Phase 9 : Documentation (30min)
- [ ] README.md complet
- [ ] Guide installation
- [ ] Guide utilisation
- [ ] Troubleshooting

---

## 🐛 Gestion des Erreurs

### Stratégies de Robustesse

1. **Rate Limiting** : Respecter les délais entre requêtes
2. **Retry Logic** : 3 tentatives avec backoff exponentiel
3. **Timeouts** : 30 secondes max par requête
4. **Logging** : Tous les événements dans data/logs/
5. **Fallback** : Si un scraper fail, continuer avec les autres
6. **Cache** : Éviter de re-scraper les mêmes offres
7. **Validation** : Vérifier structure des données scrapées

### Alertes

En cas d'erreur critique :
- Log l'erreur détaillée
- Envoyer email d'alerte à l'utilisateur
- Ne pas bloquer le workflow

---

## 📈 Optimisations Futures (V2)

**Après validation de la V1**, possibles améliorations :

1. **Web Interface** : Dashboard web pour consulter les offres
2. **Machine Learning** : Apprendre des choix utilisateur pour améliorer le scoring
3. **Alertes Temps Réel** : Notification instantanée pour offres très pertinentes
4. **Intégration LinkedIn** : Scraping ou API payante
5. **Auto-Apply** : Candidature automatique sur certains sites
6. **Analytics Avancés** : Tableaux de bord prédictifs
7. **Multi-Utilisateurs** : Système pour plusieurs chercheurs d'emploi

---

## 🎯 Critères de Succès

Le système sera considéré comme réussi si :

✅ **Fonctionnel** :
- Scrape au moins 3 des 4 sites cibles
- Filtre correctement selon les critères
- Analyse IA fonctionne sans erreur
- Email quotidien envoyé de façon fiable

✅ **Qualité** :
- < 10% de faux positifs (offres non pertinentes avec score >70)
- > 80% de vraies opportunités détectées (pas de faux négatifs critiques)
- Temps d'exécution < 10 minutes

✅ **Fiabilité** :
- Fonctionne 7j/7 sans intervention manuelle
- Logs clairs en cas d'erreur
- Récupération automatique des erreurs non critiques

---

## 💡 Conseils de Développement

1. **Commencer Simple** : Implémenter d'abord Indeed + filtrage basique + Google Sheet
2. **Tester Régulièrement** : Valider chaque module avant de passer au suivant
3. **Gérer les Cas d'Erreur** : Les sites web changent, prévoir des fallbacks
4. **Documenter** : Commenter le code pour faciliter la maintenance
5. **Versionner** : Git commit réguliers avec messages clairs

---

## 📞 Contact

**Utilisateur** : Claude Varas  
**Email** : varas.cundo@gmail.com  
**GitHub** : (à compléter si applicable)

---

## 🔐 Sécurité & Confidentialité

- ⚠️ **Ne jamais commit les clés API** dans le repo
- ⚠️ Utiliser GitHub Secrets pour les credentials
- ⚠️ .env dans .gitignore
- ✅ Repo privé recommandé
- ✅ Rotation régulière des clés API

---

**Dernière mise à jour** : {date_generation}

**Version** : 1.0

**Statut** : Ready for Development 🚀
