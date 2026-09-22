from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_runtime_image_contains_front_export_module():
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    copy_commands = [
        line.split()
        for line in dockerfile.splitlines()
        if line.strip().startswith("COPY ")
    ]

    assert any("front_export.py" in command[1:-1] for command in copy_commands)


def test_runtime_image_contains_spontaneous_prospection_modules():
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    copy_commands = [
        line.split()
        for line in dockerfile.splitlines()
        if line.strip().startswith("COPY ")
    ]

    copied_sources = {
        source
        for command in copy_commands
        for source in command[1:-1]
    }
    assert {
        "pipeline_spontaneous.py",
        "opportunity.py",
        "company_analysis/",
        "prospectors/",
    } <= copied_sources


def test_agency_target_uses_runtime_python_binary():
    service = (
        PROJECT_ROOT / "server" / "services" / "agenciesService.js"
    ).read_text(encoding="utf-8")

    assert "process.env.PYTHON_BIN || 'python3'" in service
    assert "'python3.10'" not in service


def test_agency_target_uses_an_async_task_contract():
    routes = (
        PROJECT_ROOT / "server" / "routes" / "applications.js"
    ).read_text(encoding="utf-8")
    app = (PROJECT_ROOT / "front" / "src" / "App.jsx").read_text(encoding="utf-8")

    assert "enqueueAgencyTask" in routes
    assert "activeAgencyTasksByDomain" in routes
    assert "router.get('/agencies/target/status/:taskId'" in routes
    assert "res.status(202).json" in routes
    assert "waitForAgencyTarget" in app
    assert "/api/agencies/target/status/" in app
    assert "networkErrors >= 5" in app

    service = (
        PROJECT_ROOT / "server" / "services" / "agenciesService.js"
    ).read_text(encoding="utf-8")
    assert "COMPANY_PREPARE_TIMEOUT_MS" in service
    assert "20 * 60 * 1000" in service


def test_job_cards_use_a_stable_react_key():
    app_source = (PROJECT_ROOT / "front" / "src" / "App.jsx").read_text(
        encoding="utf-8"
    )

    assert "<article key={prepareKey}" in app_source
    assert "<article key={i}" not in app_source


def test_runtime_installs_pdf_parser_and_assessment_config():
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    config = PROJECT_ROOT / "config" / "cv_assessment.json"

    assert "pypdf==" in requirements
    assert "COPY config/ ./config/" in dockerfile
    assert config.exists()


def test_cv_page_exposes_ai_review_and_regeneration():
    manual_view = (PROJECT_ROOT / "front" / "src" / "ManualCvView.jsx").read_text(encoding="utf-8")
    assessment = (PROJECT_ROOT / "front" / "src" / "CvAssessment.jsx").read_text(encoding="utf-8")

    assert "Régénérer avec les corrections" in manual_view
    assert "job-search:last-manual-cv-result" in manual_view
    assert "Créer un nouveau CV" in manual_view
    assert "localStorage.removeItem(LAST_RESULT_STORAGE_KEY)" in manual_view
    assert "Consignes personnelles pour ce CV" in manual_view
    assert 'name="candidate_instructions"' in manual_view
    assert "candidate_instructions: form.candidate_instructions.trim()" in manual_view
    assert "manual-cv-instructions textarea::placeholder" in (
        PROJECT_ROOT / "front" / "src" / "App.css"
    ).read_text(encoding="utf-8")
    assert "Jugement détaillé des agents IA" in assessment
    assert "Pourquoi le CV doit être corrigé" in assessment


def test_agency_search_history_is_exposed_by_routes_not_only_static_files():
    """Le front doit pouvoir distinguer « pas encore d'index » de « index vide ».

    Un 404 sur un fichier statique ne dit ni l'un ni l'autre : d'où des routes
    JSON dédiées, avec `latest.json` conservé en repli de compatibilité.
    """
    routes = (
        PROJECT_ROOT / "server" / "routes" / "applications.js"
    ).read_text(encoding="utf-8")
    service = (
        PROJECT_ROOT / "server" / "services" / "agenciesService.js"
    ).read_text(encoding="utf-8")

    assert "router.get('/agencies/searches'" in routes
    assert "router.get('/agencies/searches/:searchId'" in routes
    assert "router.get('/agencies/analyses'" in routes
    # Le ciblage porte sur la recherche affichée, jamais sur « la plus récente ».
    assert "req.body?.search_id" in routes
    assert "readSearchPayload(searchId)" in routes

    assert "SEARCH_ID_PATTERN" in service
    assert "Recherches disponibles" in service
    # `data/agency_analyses.json` n'est jamais servi brut ni rendu modifiable.
    assert "readPersistedAnalyses" in service
    assert "writeFileSync(ANALYSES_PATH" not in service


def test_agencies_view_carries_the_search_context():
    app = (PROJECT_ROOT / "front" / "src" / "App.jsx").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "front" / "src" / "App.css").read_text(encoding="utf-8")

    assert "/api/agencies/searches" in app
    assert "agency-search-picker" in app
    assert "AGENCY_SEARCH_STORAGE_KEY" in app
    # Le ciblage envoie l'identifiant de la recherche consultée.
    assert "JSON.stringify({ domain, search_id: selectedId })" in app
    # Repli de compatibilité : une installation sans index reste utilisable.
    assert "/agencies/latest.json" in app
    # Les agences vérifiées restent l'affichage par défaut ; les candidats registre
    # incertains sont accessibles mais ne polluent plus la vue principale.
    assert "categoryFilter, setCategoryFilter] = useState('agence')" in app
    assert "Incertains registre" in app
    assert "agencyCategoryLabel" in app
    assert "agencyScoreLabel" in app
    # Une passe terminée pendant que l'écran reste ouvert devient visible sans
    # rechargement manuel et sans réponse HTTP mise en cache.
    assert "window.setInterval(load, 15000)" in app
    assert "if (changed) setSelectedId(latestId)" in app
    assert "cache: 'no-store'" in app
    # Les anciens snapshots ne doivent plus présenter une cible purement CSV
    # comme si elle avait été découverte pendant la passe.
    assert "origins.length === 1 && origins[0] === 'csv'" in app
    assert ".agency-search-picker" in css
    assert ".agency-category-filter" in css


def test_the_durable_conventions_name_the_agency_runbook():
    """Un nouvel agent doit trouver sources, limites et règles anti-invention."""
    runbook = PROJECT_ROOT / "docs" / "AGENCY_PROSPECTING_RUNBOOK.md"
    assert runbook.exists()
    text = runbook.read_text(encoding="utf-8")

    for expected in (
        "donnée non fiable",           # texte web
        "ne se déduit jamais",          # adresse
        "pas juge d'activité",          # registre
        "formation",                    # catégories
        "DEFAULT_MAX_CALLS",            # plafond de coût IA
        "pinned",                       # rétention
        "Reprise après incident",
    ):
        assert expected in text, f"runbook incomplet : « {expected} » absent"

    claude_md = (PROJECT_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "AGENCY_PROSPECTING_RUNBOOK.md" in claude_md
    schema = (PROJECT_ROOT / "docs" / "AGENCIES_SCHEMA.md").read_text(encoding="utf-8")
    assert "search_id" in schema and "index.json" in schema
