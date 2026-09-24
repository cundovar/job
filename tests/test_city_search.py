"""Mode ville générique : prospecter une commune sans toucher au code.

Ces tests figent les quatre critères de la phase 4, et une seule idée derrière
eux : `ZONES` n'était pas la liste des villes prospectables, mais elle se lisait
comme telle. On en tirait deux conclusions fausses — « Lille n'est pas
disponible » et « ajouter une ville demande une modification du source » — et la
seconde a déjà produit le pire des contournements : des agences inventées pour
combler un périmètre qu'on croyait inaccessible.

Tout tourne hors ligne : l'API Découpage administratif est remplacée par
`tests/fixtures/geo_communes.json`, qui contient de vraies réponses (Montreuil a
bien trois homonymes exacts, Lille a bien cinq codes postaux).
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import urllib.parse
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "geo_communes.json"


def load_module(name: str):
    """`tools/` n'est pas un package : on charge le fichier directement."""
    path = PROJECT_ROOT / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def geo() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def fake_opener(geo):
    """Rejoue geo.api.gouv.fr depuis la fixture, et compte les appels.

    Le compteur sert à vérifier qu'une ville introuvable ne déclenche **aucune**
    requête de repli : chercher ailleurs sans le dire rendrait une passe qui a
    l'air ciblée et ne l'est pas.
    """
    calls: list[str] = []

    def opener(url: str, timeout: int) -> str:
        calls.append(url)
        parsed = urllib.parse.urlparse(url)
        if parsed.path.startswith("/departements/"):
            parts = parsed.path.strip("/").split("/")
            code = parts[1] if len(parts) > 1 else ""
            department = geo["departements"].get(code, {})
            if parts[-1] == "communes":
                rows = department.get("communes")
                if rows is None:
                    rows = [
                        row for rows in geo["communes"].values()
                        for row in rows
                        if row.get("codeDepartement") == code
                    ]
                return json.dumps(rows)
            return json.dumps({key: department.get(key) for key in ("code", "nom")})
        if parsed.path == "/departements":
            params = urllib.parse.parse_qs(parsed.query)
            wanted = (params.get("nom", [""])[0]).strip().casefold()
            rows = [
                row for row in geo["departements"].values()
                if not wanted or row.get("nom", "").casefold() == wanted
            ]
            return json.dumps(rows)
        params = urllib.parse.parse_qs(parsed.query)
        key = (params.get("nom", [""])[0]).strip().lower()
        rows = geo["communes"].get(key, [])
        wanted = params.get("codeDepartement", [""])[0]
        if wanted:
            rows = [row for row in rows if row.get("codeDepartement") == wanted]
        return json.dumps(rows)

    opener.calls = calls  # type: ignore[attr-defined]
    return opener


# ── Critère 1 : Montreuil et Lille résolus, sans entrée ajoutée à ZONES ───────


def test_montreuil_resolves_to_its_real_insee_and_postal_code(fake_opener):
    """Montreuil (93) = INSEE 93048, code postal 93100.

    Le plan de phase annonçait « 93066 » : ce code n'est pas celui de Montreuil.
    Le test fige ce que l'API publie, pas ce que le plan supposait — c'est
    exactement la discipline que le reste du projet applique aux adresses.
    """
    resolver = load_module("city_resolver")

    commune = resolver.resolve_city("Montreuil", "93", opener=fake_opener)

    assert commune["insee"] == "93048"
    assert commune["postal_codes"] == ["93100"]
    assert commune["departement"] == "93"
    assert commune["departement_name"] == "Seine-Saint-Denis"
    # GeoJSON publie [longitude, latitude] : inversé, Montreuil partirait au
    # large de la Somalie et la première distance mesurée serait absurde.
    assert 48.0 < commune["latitude"] < 49.5
    assert 2.0 < commune["longitude"] < 3.0


def test_lille_resolves_to_its_own_perimeter_and_all_its_postal_codes(fake_opener):
    """Lille n'a jamais été « indisponible » : elle n'avait pas de préréglage."""
    resolver = load_module("city_resolver")

    commune = resolver.resolve_city("Lille", opener=fake_opener)

    assert commune["insee"] == "59350"
    # Cinq codes postaux : n'en garder qu'un exclurait du périmètre des adresses
    # lilloises parfaitement lisibles.
    assert set(commune["postal_codes"]) == {"59000", "59160", "59260", "59777", "59800"}
    assert resolver.city_zone_key(commune) == "ville-lille-59"


def test_department_resolves_by_code_and_name_without_static_catalogue(fake_opener):
    resolver = load_module("city_resolver")

    by_code = resolver.resolve_department("93", opener=fake_opener)
    by_name = resolver.resolve_department("Seine-Saint-Denis", opener=fake_opener)

    assert by_code["code"] == "93"
    assert by_code["name"] == "Seine-Saint-Denis"
    assert by_code["commune_codes"] == ["93048"]
    assert by_name["code"] == by_code["code"]
    assert resolver.department_zone_key(by_code) == "departement-93-seine-saint-denis"


@pytest.mark.parametrize(
    "value,code",
    [("2A", "2A"), ("971", "971")],
)
def test_department_codes_special_and_overseas_are_not_forced_to_numeric(fake_opener, value, code):
    resolver = load_module("city_resolver")

    department = resolver.resolve_department(value, opener=fake_opener)

    assert department["code"] == code
    assert department["communes"]


def test_a_city_search_adds_nothing_to_the_static_zones(fake_opener):
    """Le périmètre d'une ville vit à l'exécution, pas dans une constante."""
    v2 = load_module("agency_prospecting_v2")
    before = set(v2.ZONES)

    zone_key, zone_cfg, commune = v2.resolve_perimeter(
        {"city": "Lille", "departement": ""}, opener=fake_opener
    )

    assert set(v2.ZONES) == before, "ZONES est un jeu de préréglages, pas un catalogue de villes"
    assert zone_key not in v2.ZONES
    assert v2.zone_config(zone_key) is zone_cfg
    assert commune["insee"] == "59350"
    assert zone_cfg["insee"] == "59350"


def test_the_static_zones_stay_the_four_historical_presets():
    """Régression documentaire : quatre préréglages, et rien de plus.

    Si quelqu'un ajoute une ville ici, c'est que le mode `--ville` a cessé de
    fonctionner ou de se voir — et le réflexe « modifier le code pour chercher
    ailleurs » revient.
    """
    v2 = load_module("agency_prospecting_v2")

    assert set(v2.ZONES) == {"ile-de-france", "ouest-paris", "paris-19", "paris-20"}


# ── Critère 1 (suite) : la piste formation ne se perd pas en route ────────────


def test_both_query_families_are_generated_and_kept(fake_opener):
    """Deux familles, étiquetées, conservées de la requête au résultat.

    Un organisme de formation n'est pas une agence ratée : c'est une cible
    différente, avec son vocabulaire. Fondue dans la famille « agence », elle
    n'était jamais trouvée.
    """
    resolver = load_module("city_resolver")
    commune = resolver.resolve_city("Montreuil", "93", opener=fake_opener)

    families = resolver.query_families(commune)

    assert set(families) == {resolver.FAMILY_AGENCY, resolver.FAMILY_FORMATION}
    assert families[resolver.FAMILY_AGENCY], "aucune requête d'agence"
    assert families[resolver.FAMILY_FORMATION], "la piste formation a disparu"
    # La ville doit apparaître dans chaque requête, sinon la passe n'est ciblée
    # que par son titre.
    for queries in families.values():
        for query in queries:
            assert "Montreuil" in query, query
    assert any("RGAA" in q or "formation" in q.lower() for q in families[resolver.FAMILY_FORMATION])
    # À plat, aucune requête ne se perd entre les familles et l'exécution.
    assert resolver.city_queries(commune) == (
        families[resolver.FAMILY_AGENCY] + families[resolver.FAMILY_FORMATION]
    )


# ── L'homonyme n'est jamais tranché à la place de l'utilisateur ───────────────


def test_an_ambiguous_city_names_its_candidates_instead_of_picking_one(fake_opener):
    """Montreuil existe en 93, en 85 et en 28. Le plus peuplé n'est pas « le bon »."""
    resolver = load_module("city_resolver")

    with pytest.raises(resolver.AmbiguousCityError) as excinfo:
        resolver.resolve_city("Montreuil", opener=fake_opener)

    message = str(excinfo.value)
    assert "--departement" in message
    for code in ("93", "85", "28"):
        assert code in message, f"le département {code} doit être nommé : {message}"
    assert {c["insee"] for c in excinfo.value.candidates} == {"93048", "85148", "28267"}


def test_a_near_name_is_never_taken_for_the_requested_city(fake_opener):
    """« Montreuil-Juigné » n'est pas « Montreuil ».

    La recherche de l'API est approximative ; seule l'égalité du nom normalisé
    désigne la commune demandée. Une comparaison en sous-chaîne prospecterait le
    Maine-et-Loire en croyant faire la Seine-Saint-Denis.
    """
    resolver = load_module("city_resolver")

    commune = resolver.resolve_city("Montreuil", "93", opener=fake_opener)

    assert commune["name"] == "Montreuil"
    assert commune["insee"] != "49214"


def test_an_unknown_city_names_what_exists_and_falls_back_on_nothing(fake_opener):
    resolver = load_module("city_resolver")

    with pytest.raises(resolver.CityResolutionError) as excinfo:
        resolver.resolve_city("Zzzzville", opener=fake_opener)

    message = str(excinfo.value)
    assert "Zzzzville" in message
    # Nommer ce qui existe : un message vide se relit « il n'y a rien », et
    # c'est cette lecture qui a fait inventer des agences.
    assert "Montreuil" in message and "Lille" in message
    assert "Aucune recherche de repli" in message
    # Et le dire ne suffit pas : aucune seconde requête n'a été lancée.
    assert len(fake_opener.calls) == 1


# ── Critère 3 : le périmètre se juge sur une preuve, pas sur un nom ───────────


def test_a_city_name_found_in_a_page_never_counts_as_an_address(fake_opener):
    """« Nous intervenons à Montreuil » ne fait pas une agence montreuilloise."""
    resolver = load_module("city_resolver")
    commune = resolver.resolve_city("Montreuil", "93", opener=fake_opener)

    mention = {"name": "Agence lyonnaise", "zone_match": "tier1", "how": "", "postal_code": None}
    level, evidence = resolver.locate_in_city(mention, commune)

    assert level == resolver.PERIMETER_MENTION
    assert evidence, "un niveau sans preuve citée ne se relit pas"
    assert not resolver.in_perimeter(mention, commune)


@pytest.mark.parametrize(
    "agency, expected",
    [
        ({"postal_code": "93100", "how": "adresse", "zone_match": "tier1"}, "adresse"),
        ({"postal_code": "93100", "how": "contact/legales", "zone_match": "none"}, "adresse"),
        ({"postal_code": "93100", "how": "siège (registre)", "zone_match": "none"}, "registre"),
        ({"commune_code": "93048", "how": "", "zone_match": "none"}, "registre"),
        # Une position déduite du centre de la ville n'est pas une adresse : le
        # code postal ne vient d'aucune ligne lue. Elle retombe au mieux sur la
        # mention, qui ne fait entrer personne dans le périmètre.
        ({"postal_code": "93100", "how": "ville/arr (~centre)", "zone_match": "tier1"}, "mention"),
        ({"postal_code": "59000", "how": "adresse", "zone_match": "tier1"}, "mention"),
        ({"postal_code": None, "how": "", "zone_match": "none"}, "aucun"),
    ],
)
def test_the_perimeter_level_says_what_established_it(fake_opener, agency, expected):
    resolver = load_module("city_resolver")
    commune = resolver.resolve_city("Montreuil", "93", opener=fake_opener)

    level, _ = resolver.locate_in_city(agency, commune)

    assert level == expected


def test_deep_crawl_only_looks_at_candidates_linked_to_the_city(fake_opener):
    """Le crawl profond coûte le plus cher : il se réserve aux candidats locaux.

    Chaque abandon est motivé. Un candidat qui disparaît sans trace est
    redécouvert au run suivant, réévalué, et finit par repasser.
    """
    v2 = load_module("agency_prospecting_v2")
    _, zone_cfg, _ = v2.resolve_perimeter({"city": "Montreuil", "departement": "93"}, opener=fake_opener)

    candidates = [
        {"base": "https://locale.fr", "text": "Agence web à Montreuil depuis 2010"},
        {"base": "https://registre.fr", "text": "Studio", "commune_code": "93048"},
        {"base": "https://ailleurs.fr", "text": "Agence web à Bordeaux"},
        {"base": "https://injoignable.fr", "text": ""},
        {"base": "https://exclue.fr", "text": "Agence web à Montreuil"},
    ]

    keep, dropped = v2.select_for_deep_crawl(
        candidates, zone_cfg, excluded_hosts={"exclue.fr": "plateforme"}
    )

    assert {c["base"] for c in keep} == {"https://locale.fr", "https://registre.fr"}
    motifs = {c["base"]: c["motif"] for c in dropped}
    assert set(motifs) == {"https://ailleurs.fr", "https://injoignable.fr", "https://exclue.fr"}
    for base, motif in motifs.items():
        assert motif.strip(), f"{base} écarté sans motif"
    assert "Montreuil" in motifs["https://ailleurs.fr"]


# ── Critère 3 (suite) : les étapes se voient, sans donnée personnelle ─────────


def test_the_steps_publish_durations_and_counters_only():
    """Un run lent et un run bloqué se ressemblent tant qu'aucune étape ne parle.

    Mais ces étapes voyagent jusqu'au statut HTTP : elles ne portent que des
    nombres. Un nom d'entreprise ou une adresse glissés ici sortiraient du dépôt.
    """
    v2 = load_module("agency_prospecting_v2")
    ticks = iter([0.0, 1.5, 2.0, 2.0])
    log = v2.StepLog(clock=lambda: next(ticks))

    with log.step("decouverte_web") as volumes:
        volumes["hotes"] = 75
        volumes["agence"] = "Fabrique du Net"  # doit être refusé

    running = log.start("crawl")
    steps = log.as_list()

    assert steps[0]["step"] == "decouverte_web"
    assert steps[0]["duration_ms"] == 1500
    assert steps[0]["volumes"] == {"hotes": 75}, "seuls des nombres sont publiés"
    # Une étape ouverte se distingue d'une étape instantanée.
    assert steps[1]["duration_ms"] is None
    assert isinstance(running, int)
    # Aucun temps interne ne fuit dans le JSON publié.
    assert all(set(entry) == {"step", "started_at", "duration_ms", "volumes"} for entry in steps)


def test_every_published_step_has_a_declared_name():
    v2 = load_module("agency_prospecting_v2")

    for name in ("resolution", "registre", "decouverte_web", "crawl", "geocodage", "ia", "publication"):
        assert name in v2.STEP_NAMES


# ── Critère 2 : la ligne de commande refuse plutôt que d'arbitrer ─────────────


def test_city_and_zone_together_are_refused_never_arbitrated():
    """Accepter les deux obligerait à en ignorer un en silence."""
    v2 = load_module("agency_prospecting_v2")

    with pytest.raises(SystemExit) as excinfo:
        v2.parse_cli(["--ville", "Lille", "--zone", "paris-20"])

    assert excinfo.value.code == 2


def test_department_only_mode_has_no_historical_zone_fallback():
    v2 = load_module("agency_prospecting_v2")

    options = v2.parse_cli(["--departement", "93"])

    assert options["departement"] == "93"
    assert options["zone"] == ""


def test_zone_and_department_together_are_refused_never_arbitrated():
    v2 = load_module("agency_prospecting_v2")

    with pytest.raises(SystemExit) as excinfo:
        v2.parse_cli(["--zone", "paris-20", "--departement", "93"])

    assert excinfo.value.code == 2


def test_an_unknown_zone_names_the_presets_and_points_at_the_city_mode(capsys):
    v2 = load_module("agency_prospecting_v2")

    with pytest.raises(SystemExit):
        v2.parse_cli(["--zone", "lille"])

    message = capsys.readouterr().err
    assert "paris-20" in message and "ile-de-france" in message
    # Sans cette phrase, « zone inconnue » se lit « ville non supportée ».
    assert "--ville" in message


def test_the_city_mode_leaves_the_zone_empty_instead_of_defaulting():
    v2 = load_module("agency_prospecting_v2")

    options = v2.parse_cli(["--ville", "Quimper", "--departement", "29"])

    assert options["city"] == "Quimper"
    assert options["departement"] == "29"
    # Le défaut historique « ile-de-france » ne doit pas se rallumer derrière une
    # ville : la passe publierait un périmètre que personne n'a demandé.
    assert options["zone"] == ""


# ── Critère 4 : une ville absente du code marche sans modifier le code ────────


def test_a_city_absent_from_the_source_produces_queries_and_a_search_id(fake_opener, tmp_path):
    """Quimper n'est écrite nulle part dans le dépôt. Elle doit marcher quand même.

    Le test va jusqu'à la publication : une passe qui produit des requêtes mais
    aucun identifiant ne serait pas relisible, et « relire la dernière » est
    précisément ce qui mélangeait deux villes.
    """
    v2 = load_module("agency_prospecting_v2")
    source = (PROJECT_ROOT / "tools" / "agency_prospecting_v2.py").read_text(encoding="utf-8")
    assert "Quimper" not in source, "la ville de test ne doit pas être écrite dans le code"

    zone_key, zone_cfg, commune = v2.resolve_perimeter(
        {"city": "Quimper", "departement": ""}, opener=fake_opener
    )
    queries = v2.city_queries(commune)

    assert commune["insee"] == "29232"
    assert zone_key == "ville-quimper-29"
    assert any("Quimper" in q for q in queries)
    assert len(queries) >= 4

    payload = {
        "ok": True,
        "generated_at": "2026-09-22T10:00:00",
        "zone": zone_key,
        "zone_label": zone_cfg["label"],
        "city": commune,
        "total": 1,
        "agencies": [{"name": "Studio Cornouaille", "website": "https://exemple.bzh",
                      "address": "1 rue de la Providence", "postal_code": "29000",
                      "how": "adresse"}],
        "search_id": v2.make_search_id(zone_key, "20260922-100000"),
    }
    published = v2.publish_search(payload, tmp_path)

    index = json.loads((tmp_path / v2.SEARCH_INDEX_NAME).read_text(encoding="utf-8"))
    assert published["search_id"].startswith("ville-quimper-29")
    assert any(entry["search_id"] == published["search_id"] for entry in index["searches"])
    assert (tmp_path / v2.SEARCHES_DIRNAME / f"{published['search_id']}.json").exists()


def test_two_cities_do_not_share_a_search_id(fake_opener):
    """Sans le département dans la clé, deux Montreuil partageraient un historique."""
    v2 = load_module("agency_prospecting_v2")

    lille_key, _, _ = v2.resolve_perimeter({"city": "Lille"}, opener=fake_opener)
    montreuil_key, _, _ = v2.resolve_perimeter({"city": "Montreuil", "departement": "93"}, opener=fake_opener)

    assert lille_key != montreuil_key
    assert montreuil_key.endswith("-93")


# ── Critère 2 : Hermes ne confond pas les tâches de deux villes ───────────────


def test_the_server_tells_two_city_searches_apart():
    """Deux villes lancées coup sur coup ne doivent pas se reconnaître entre elles.

    La déduplication protège d'un double clic ; si elle regarde seulement la
    zone, elle rend à Lille le `task_id` de Montreuil et le suivi ment.
    """
    script = """
      import { sameProspectingRequest } from './server/services/agenciesService.js';
      const task = { zone: null, city: 'Montreuil', departement: '93', radiusM: null };
      console.log(JSON.stringify({
        identique: sameProspectingRequest(task, { zone: null, city: 'Montreuil', departement: '93', radiusM: null }),
        autreVille: sameProspectingRequest(task, { zone: null, city: 'Lille', departement: null, radiusM: null }),
        autreDepartement: sameProspectingRequest(task, { zone: null, city: 'Montreuil', departement: '85', radiusM: null }),
        autreRayon: sameProspectingRequest(task, { zone: null, city: 'Montreuil', departement: '93', radiusM: 2000 }),
      }));
    """
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    out = json.loads(completed.stdout)

    assert out["identique"] is True
    assert out["autreVille"] is False
    assert out["autreDepartement"] is False, "deux Montreuil ne sont pas la même passe"
    assert out["autreRayon"] is False


def test_a_city_name_is_never_passed_through_as_a_free_expression():
    """Le nom de ville devient un argument de ligne de commande : il se valide.

    Le refus arrive **avant** tout lancement de processus — la validation n'est
    pas une politesse d'affichage.
    """
    # Aucun cas ne doit être *valide* ici : un nom accepté lancerait une vraie
    # passe de prospection, qui dure des minutes et sort sur le réseau.
    script = """
      import { runProspecting } from './server/services/agenciesService.js';
      const essais = ['Lille; rm -rf /', '../../etc/passwd', '$(whoami)', '--no-ai'];
      const out = {};
      for (const ville of essais) {
        try {
          await runProspecting({ city: ville, departement: null, radiusM: null, zone: null });
          out[ville] = 'ACCEPTE';
        } catch (err) {
          out[ville] = err.message.startsWith('Ville invalide') ? 'REFUSE' : 'AUTRE';
        }
      }
      try {
        await runProspecting({ city: 'Montreuil', departement: '93; ls', radiusM: null, zone: null });
        out.departement = 'ACCEPTE';
      } catch (err) {
        out.departement = err.message.startsWith('Département invalide') ? 'REFUSE' : 'AUTRE';
      }
      console.log(JSON.stringify(out));
    """
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    out = json.loads(completed.stdout)

    # Le dernier cas compte double : un nom qui commence par `--` deviendrait un
    # drapeau du script au lieu d'une valeur.
    for essai in ("Lille; rm -rf /", "../../etc/passwd", "$(whoami)", "--no-ai"):
        assert out[essai] == "REFUSE", f"{essai} : {out[essai]}"
    assert out["departement"] == "REFUSE"


def test_hermes_can_launch_follow_and_reread_a_city_search():
    """Le trio `agency_search` → `agency_status` → `agency_list` doit tenir la ville."""
    spec = importlib.util.spec_from_file_location(
        "hermes_mcp_server", PROJECT_ROOT / "hermes_mcp_server.py"
    )
    hermes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hermes)

    search = hermes.TOOLS["agency_search"]["inputSchema"]["properties"]
    assert "city" in search and "departement" in search
    # Dire dans la description que toute commune passe : un agent qui lit
    # « zone » comme « la liste des villes supportées » conclut qu'on ne peut
    # pas chercher ailleurs, et relance une recherche d'annonces faute de mieux.
    assert "city" in hermes.TOOLS["agency_search"]["description"]
    assert "commune" in search["city"]["description"].lower()
    assert "prereglage" in search["zone"]["description"].lower()

    # Le statut rend l'identifiant, la liste le consomme : sans ce fil, relire
    # « la dernière passe » rend une autre ville sans le dire.
    assert "search_id" in hermes.TOOLS["agency_status"]["description"]
    assert "search_id" in hermes.TOOLS["agency_list"]["inputSchema"]["properties"]
    for name in ("agency_search", "agency_status", "agency_list"):
        assert hermes.TOOLS[name]["description"].startswith("ENTREPRISES/AGENCES —")
