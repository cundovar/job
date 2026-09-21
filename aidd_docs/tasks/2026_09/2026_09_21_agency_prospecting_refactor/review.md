# Review: prospection d'agences

- **Verdict**: changes-requested
- **Diff**: `e81e325^...183853f`
- **Axes run**: code, functional, relevancy
- **Date**: 2026_09_21
- **Findings**: 0 critical, 4 warning, 0 minor

## Phases

### Phase 1 — Arrêter l'hémorragie

- [x] Le motif `/data/` est ancré et `front/public/data/agencies/latest.json` est suivi — `.gitignore:47`, `front/public/data/agencies/latest.json:1`
- [x] Les sorties du v2 sont déduites de la racine du dépôt et `--out` existe — `tools/agency_prospecting_v2.py:33-36`, `tools/agency_prospecting_v2.py:682`
- [x] L'unité systemd documente et utilise le chemin du VPS — `deploy/job-search-cli-bridge.service:10-17`, `CLAUDE.md:78-82`
- [x] Le script de test endpoint est versionné — `test_agencies_endpoint.sh:1`

### Phase 2 — Une seule source de vérité pour les agences

- [x] Le CSV porte `adresse` et `code_postal`, et l'opportunité les propage — `config/companies.csv:1-15`, `opportunity.py:85-92`
- [x] Le seed Node et son écrasement au démarrage ont disparu — `server/index.js:45-50`
- [x] La liste d'entreprises affiche l'adresse et accepte un filtre postal strict — `hermes_commands/company_top.py:23-36`, `pipeline_spontaneous.py:108-143`
- [ ] Le CSV versionné est réellement la source de vérité de `latest.json` — le fichier suivi est un payload manuel, mais le producteur déclaré ne lit jamais `config/companies.csv` et l'écrasera à la prochaine prospection — fix

### Phase 3 — Restaurer la recherche par rayon dans le v2

- [x] `--radius` réutilise le géocodage, sépare adresse lue, approximation, hors rayon et inconnue — `tools/agency_prospecting_v2.py:379-476`, `tools/agency_prospecting_v2.py:691-702`
- [x] Le rapport conserve les listes écartées et le champ `how` — `tools/agency_prospecting_v2.py:792-815`
- [x] Les caches ne sont publiés que pour un résultat non vide — `tools/agency_prospecting_v2.py:838-843`, `tools/agency_prospecting_v2.py:890-898`

### Phase 4 — Schéma commun et fin des deux dialectes

- [x] Le schéma commun est documenté et le seed concurrent a été supprimé — `docs/AGENCIES_SCHEMA.md:1-95`, `server/index.js:45-50`
- [ ] Le producteur renseigne tous les champs obligatoires du schéma — `postal_code` n'est jamais créé par le v2, ce qui casse aussi le filtre postal de `agency_list` après une vraie passe — fix

### Phase 5 — Exposer la recherche d'agences au MCP

- [x] `agency_search`, `agency_status` et `agency_list` sont déclarés avec des descriptions explicites — `hermes_mcp_server.py:464-526`
- [x] Le serveur expose une file asynchrone et des endpoints de recherche — `server/routes/applications.js:530-595`, `server/routes/applications.js:783-812`
- [ ] Une demande de zone/rayon reçoit une tâche correspondant à ses paramètres — toute demande concurrente récupère la tâche active, même si sa zone ou son rayon diffèrent — fix
- [ ] `company_prepare` désactive réellement le CV par défaut — le schéma annonce `false`, mais le handler applique `True` lorsque l'argument est omis — fix
- [x] `_capture` détourne stdout et stderr hors du canal JSON-RPC — `hermes_mcp_server.py:27-42`

### Phase 6 — Garde-fous

- [x] Les tests ciblés couvrent racine, approximation, adresse affichée et descriptions MCP — `tests/test_agency_prospecting.py:34-165`
- [x] `CLAUDE.md` consigne les chemins, l'ignore et les règles anti-invention — `CLAUDE.md:55-87`
- [ ] Les contrats nouvellement fragiles sont testés — aucun test ne vérifie le `postal_code` produit par le v2, le défaut effectif de `company_prepare`, ni la déduplication des tâches par paramètres — fix

## Findings

| Sev | Kind | Phase | Location | Issue | Fix |
| --- | ---- | ----- | -------- | ----- | --- |
| 🟡 warning | functional | 2 | `tools/agency_prospecting_v2.py:704-769` | Le producteur unique déclaré ne charge jamais `config/companies.csv`; le `latest.json` versionné a été construit manuellement avec les sept entrées migrées et sera remplacé par les seuls résultats du crawl. La source de vérité reste donc divisée. | Injecter les entrées CSV dans le pipeline v2 avec une provenance explicite, ou générer le payload versionné par une fonction commune au lieu de le maintenir à la main. |
| 🟡 warning | functional | 4 | `tools/agency_prospecting_v2.py:396-425` | Le v2 crée `address`, `address_source` et `distance_m`, mais jamais `postal_code`. Après la première vraie prospection, `agency_list(postal_code="75020")` ne trouvera aucune entrée même lorsque l'adresse contient 75020. | Extraire le code postal depuis la même correspondance d'adresse et le stocker uniquement lorsque `address` est renseigné; ajouter un test sur le payload produit. |
| 🟡 warning | functional | 5 | `server/routes/applications.js:553-558` | Si une prospection est active, toute nouvelle demande réutilise cette tâche sans comparer `zone` ni `radius_m`; une demande Paris-20 peut ainsi recevoir les résultats d'une passe Île-de-France. | Ne dédupliquer que lorsque zone et rayon sont identiques, sinon mettre la nouvelle demande en file avec ses propres paramètres. |
| 🟡 warning | functional | 5 | `hermes_mcp_server.py:156-163` | Le schéma MCP annonce `with_cv=false` par défaut, mais un appel sans argument passe `True` au handler et relance précisément la génération longue que le plan voulait éviter. | Remplacer le défaut du handler par `False` et tester l'appel sans `with_cv`. |

## Verification

| Metric        | Value |
| ------------- | ----- |
| Verified      | 76% (16/21) |
| Files checked | `.gitignore`, `CLAUDE.md`, `config/companies.csv`, `config/companies.yaml`, `deploy/job-search-cli-bridge.service`, `docs/AGENCIES_SCHEMA.md`, `front/public/data/agencies/latest.json`, `front/src/App.jsx`, `hermes_commands/company_top.py`, `hermes_mcp_server.py`, `opportunity.py`, `pipeline_spontaneous.py`, `prospectors/csv_prospector.py`, `server/index.js`, `server/routes/applications.js`, `server/services/agenciesService.js`, `tests/test_agency_prospecting.py`, `tools/agency_prospecting_v2.py` |
| Unchecked     | CSV réellement source de `latest.json` — fix; `postal_code` produit par le v2 — fix; tâche correspondant à la zone/rayon demandés — fix; défaut effectif `with_cv=false` — fix; tests des nouveaux contrats — fix |
| Unplanned     | `config/companies.yaml` recible globalement la stratégie sur Paris-20e; cette modification vient du commit parallèle fusionné `8105035`, pas du plan de refactor joint |
