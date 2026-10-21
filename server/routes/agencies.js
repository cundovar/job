/**
 * routes/agencies.js — Prospection et ciblage d'agences (voie spontanée).
 *
 * Extrait de routes/applications.js, sans changement de comportement.
 * Les règles métier vivent dans services/agenciesService.js.
 */
import { Router } from 'express';
import path from 'path';
import { PROJECT_ROOT } from '../config.js';
import { runPython } from '../services/python.js';
import {
  normalizeDomain,
  validateDomain,
  domainMatchesAgency,
  cleanAgencyName,
  isAlreadyTargeted,
  appendToCSV,
  appendToYAML,
  measureAgency,
  prepareAgency,
  runProspecting,
  sameProspectingRequest,
  readSearchIndex,
  readSearchPayload,
  readPersistedAnalyses,
  readDecisions,
  writeDecision
} from '../services/agenciesService.js';

const AGENCY_TASK_RETENTION_MS = 60 * 60 * 1000;

// Vérifie qu'un domaine existe dans la base Agency Scout (SQLite via CLI).
// Le nom affiché vient TOUJOURS de la base, jamais du client.
async function findScoutAgencyByDomain(domain) {
  const stdout = await runPython(['-m', 'agency_scout', 'list'], {
    bin: process.env.PYTHON_BIN || 'python3',
    timeout: 20000,
  });
  const data = JSON.parse(stdout);
  return (data.agencies || []).find(a => a.domain === domain) || null;
}

export default function createAgenciesRouter() {
  const router = Router();
  const agencyTasks = new Map();
  const activeAgencyTasksByDomain = new Map();
  let agencySequence = 0;
  let agencyChain = Promise.resolve();

  function publicAgencyTask(task) {
    if (!task) return null;
    return {
      task_id: task.task_id,
      domain: task.domain,
      agency_name: task.agency_name,
      state: task.state,
      stage: task.stage,
      queued_at: task.queued_at,
      started_at: task.started_at,
      completed_at: task.completed_at,
      error: task.error,
      result: task.result,
    };
  }

  function enqueueAgencyTask({ domain, agencyName, alreadyTargeted, instructions = '' }) {
    const activeTask = activeAgencyTasksByDomain.get(domain);
    if (activeTask && ['queued', 'running'].includes(activeTask.state)) {
      return activeTask;
    }

    agencySequence += 1;
    const task = {
      task_id: `agency_${Date.now().toString(36)}_${agencySequence}`,
      domain,
      agency_name: agencyName,
      state: 'queued',
      stage: 'queued',
      queued_at: new Date().toISOString(),
      started_at: null,
      completed_at: null,
      error: null,
      result: null,
    };
    agencyTasks.set(task.task_id, task);
    activeAgencyTasksByDomain.set(domain, task);

    agencyChain = agencyChain.then(async () => {
      task.state = 'running';
      task.stage = 'mesure';
      task.started_at = new Date().toISOString();

      try {
        const measureResult = await measureAgency(agencyName);
        if (!measureResult.ok) {
          task.state = 'failed';
          task.error = measureResult.error || measureResult.reason || 'Mesure impossible';
          task.result = measureResult;
          console.error(`[agency task ${task.task_id}]`, task.error);
          return;
        }

        task.stage = 'préparation';
        const prepareResult = await prepareAgency(measureResult.number, agencyName, false, instructions);
        if (!prepareResult.ok) {
          task.state = 'failed';
          task.error = prepareResult.error || 'Préparation impossible';
          task.result = prepareResult;
          console.error(`[agency task ${task.task_id}]`, task.error);
          return;
        }

        task.state = 'completed';
        task.stage = 'completed';
        task.result = {
          ok: true,
          domain,
          number: measureResult.number,
          constats_confirmes: measureResult.constats,
          already_targeted: alreadyTargeted,
          dry: false,
        };
      } catch (err) {
        task.state = 'failed';
        task.error = String(err?.message || err || 'Erreur inconnue').trim().slice(-4000);
        console.error(`[agency task ${task.task_id}]`, task.error);
      } finally {
        task.completed_at = new Date().toISOString();
        if (activeAgencyTasksByDomain.get(domain) === task) {
          activeAgencyTasksByDomain.delete(domain);
        }
        const cleanup = setTimeout(() => {
          agencyTasks.delete(task.task_id);
        }, AGENCY_TASK_RETENTION_MS);
        cleanup.unref();
      }
    });

    return task;
  }

  // ── File de prospection d'agences ─────────────────────────────────
  // Distincte de la file `agencyTasks` : celle-ci *découvre* des agences (crawl +
  // géocodage, plusieurs minutes), l'autre *cible* une agence déjà connue.
  const searchTasks = new Map();
  let searchSequence = 0;
  let searchChain = Promise.resolve();
  let activeSearchTask = null;

  function publicSearchTask(task) {
    if (!task) return null;
    return {
      task_id: task.task_id,
      zone: task.zone,
      // Ville demandée et ville résolue restent distinctes : « Montreuil »
      // demandé, « Montreuil (93) » résolu. Les confondre masquerait une
      // résolution qui aurait choisi un autre département que celui voulu.
      city: task.city,
      departement: task.departement,
      resolved_city: task.result?.city || null,
      resolved_department: task.result?.department || null,
      radius_m: task.radius_m,
      // Identifiant de la recherche produite : le front sait quoi sélectionner
      // au retour, sans deviner « la plus récente ».
      search_id: task.result?.search_id || null,
      // Étapes mesurées par le script : de quoi distinguer un run lent d'un run
      // bloqué pendant les minutes où il n'y a rien d'autre à afficher.
      steps: task.result?.steps || [],
      state: task.state,
      queued_at: task.queued_at,
      started_at: task.started_at,
      completed_at: task.completed_at,
      error: task.error,
      result: task.result,
    };
  }

  function enqueueSearchTask({ zone = null, city = null, departement = null, radiusM }) {
    // Une seule prospection à la fois : deux crawls concurrents se disputeraient
    // le quota de géocodage Nominatim et écriraient tous deux latest.json.
    // Deux villes différentes restent deux tâches : elles s'exécutent l'une
    // après l'autre, sans jamais partager un task_id ni un résultat.
    const duplicate = [...searchTasks.values()].find(task =>
      ['queued', 'running'].includes(task.state)
      && sameProspectingRequest(task, { zone, city, departement, radiusM })
    );
    if (duplicate) {
      return duplicate;
    }

    searchSequence += 1;
    const task = {
      task_id: `agency_search_${Date.now().toString(36)}_${searchSequence}`,
      zone,
      city,
      departement,
      radius_m: radiusM,
      state: 'queued',
      queued_at: new Date().toISOString(),
      started_at: null,
      completed_at: null,
      error: null,
      result: null,
    };
    searchTasks.set(task.task_id, task);
    activeSearchTask = task;

    searchChain = searchChain.then(async () => {
      task.state = 'running';
      task.started_at = new Date().toISOString();
      try {
        task.result = await runProspecting({ zone, city, departement, radiusM });
        task.state = 'completed';
      } catch (err) {
        task.state = 'failed';
        task.error = String(err?.message || err || 'Erreur inconnue').trim().slice(-4000);
        console.error(`[agency search ${task.task_id}]`, task.error);
      } finally {
        task.completed_at = new Date().toISOString();
        if (activeSearchTask === task) activeSearchTask = null;
        const cleanup = setTimeout(() => {
          searchTasks.delete(task.task_id);
        }, AGENCY_TASK_RETENTION_MS);
        cleanup.unref();
      }
    });

    return task;
  }

  // POST /api/agencies/search — Lance une passe de prospection (découverte)
  // Répond 202 : le crawl et les géocodages durent plusieurs minutes.
  router.post('/agencies/search', (req, res) => {
    const city = String(req.body?.city || '').trim();
    const departement = String(req.body?.departement || '').trim();
    const rawZone = String(req.body?.zone || '').trim();
    const radiusM = req.body?.radius_m ?? null;

    if (city && rawZone) {
      return res.status(400).json({
        error: 'city et zone sont exclusifs : zone rejoue un préréglage historique, '
          + 'city résout une commune réelle. Envoie l’un des deux.',
      });
    }
    if (rawZone && departement) {
      return res.status(400).json({
        error: 'zone et departement sont exclusifs : choisis un préréglage ou un département.',
      });
    }
    // Sans ville ni zone, on refuse : le défaut historique « ile-de-france » a
    // déjà lancé une passe non demandée quand un transport perdait les
    // arguments (incident du 23/09/2026). Le client doit nommer son périmètre.
    if (!city && !rawZone && !departement) {
      return res.status(400).json({
        error: 'Périmètre manquant : envoie city, departement ou zone.',
      });
    }
    if (departement && radiusM != null) {
      return res.status(400).json({
        error: 'radius_m n’est pas disponible avec un département seul.',
      });
    }
    const zone = city || departement ? null : rawZone;

    if (radiusM != null && (!Number.isInteger(Number(radiusM)) || Number(radiusM) <= 0)) {
      return res.status(400).json({ error: 'radius_m doit être un nombre de mètres positif' });
    }

    try {
      const task = enqueueSearchTask({
        zone,
        city: city || null,
        departement: departement || null,
        radiusM: radiusM == null ? null : Number(radiusM),
      });
      res.status(202).json({
        accepted: true,
        task_id: task.task_id,
        status: publicSearchTask(task),
      });
    } catch (err) {
      res.status(400).json({ error: err.message });
    }
  });

  // GET /api/agencies/search/status/:taskId — Suit la passe de prospection
  router.get('/agencies/search/status/:taskId', (req, res) => {
    const task = searchTasks.get(req.params.taskId);
    if (!task) {
      return res.status(404).json({ error: 'Tâche de prospection introuvable ou expirée' });
    }
    res.json(publicSearchTask(task));
  });

  // GET /api/agencies/searches — Index des recherches publiées (le plus récent d'abord)
  // Route JSON plutôt que fichier statique : le front doit pouvoir distinguer
  // « pas encore d'index » de « index vide », ce qu'un 404 statique ne dit pas.
  router.get('/agencies/searches', (_req, res) => {
    try {
      res.json(readSearchIndex());
    } catch (err) {
      console.error('[GET /agencies/searches]', err.message);
      res.status(500).json({ error: err.message });
    }
  });

  // GET /api/agencies/searches/:searchId — Résultats d'UNE recherche
  // `latest` reste accepté comme alias de compatibilité.
  router.get('/agencies/searches/:searchId', (req, res) => {
    try {
      const { payload, search_id, source } = readSearchPayload(req.params.searchId);
      res.json({ ...payload, search_id, source });
    } catch (err) {
      // Un identifiant inconnu est refusé en nommant les recherches connues,
      // jamais par une liste vide.
      res.status(404).json({ error: err.message });
    }
  });

  // GET /api/agencies/analyses — Analyses persistées, en lecture seule
  router.get('/agencies/analyses', (_req, res) => {
    try {
      res.json(readPersistedAnalyses());
    } catch (err) {
      console.error('[GET /agencies/analyses]', err.message);
      res.status(500).json({ error: err.message });
    }
  });

  // GET /api/agencies/decisions — Tri retenu/écarté, par domaine, tous onglets
  // confondus : c'est la même agence, elle n'a pas deux avis selon la page.
  router.get('/agencies/decisions', (_req, res) => {
    try {
      res.json(readDecisions());
    } catch (err) {
      console.error('[GET /agencies/decisions]', err.message);
      res.status(500).json({ error: err.message });
    }
  });

  // PUT /api/agencies/decisions/:domain — Pose ou retire une décision.
  // `decision: null` revient à « à décider » : une décision se reprend. Rien
  // n'est supprimé de la liste — un écarté effacé serait redécouvert au scan
  // suivant, réanalysé, et reposerait la même question.
  router.put('/agencies/decisions/:domain', (req, res) => {
    try {
      const raw = req.body?.decision;
      const decision = raw === null || raw === undefined || raw === '' ? null : String(raw);
      res.json({ ok: true, ...writeDecision(req.params.domain, decision, String(req.body?.source || '')) });
    } catch (err) {
      res.status(400).json({ error: err.message });
    }
  });

  // POST /api/agencies/target — Ajoute une agence puis met la préparation en file
  // Deux sources : 'search' (défaut) relit l'agence dans la passe affichée
  // (search_id) ; 'scout' vérifie le domaine dans la base Agency Scout
  // (SQLite via CLI) — jamais le nom venu du client. La suite est commune :
  // idempotence CSV, banc d'essai, file de tâche, task_id pollable.
  router.post('/agencies/target', async (req, res) => {
    const domain = req.body?.domain;
    const dry = req.body?.dry === true;
    const source = req.body?.source === 'scout' ? 'scout' : 'search';
    // Le ciblage doit porter sur la recherche AFFICHÉE : sans search_id, deux
    // passes de villes différentes donneraient la même agence « la plus récente ».
    const searchId = req.body?.search_id ?? null;
    // Ce que le candidat demande pour CETTE candidature : un angle à appuyer
    // dans la lettre, une expérience à faire figurer au CV. Écrit dans
    // job.json avant que lettre et CV ne soient rédigés — après, il serait
    // trop tard, ils ne sont écrits qu'une fois.
    const instructions = String(req.body?.instructions || '').trim().slice(0, 2000);

    // Validation
    if (!domain || typeof domain !== 'string') {
      return res.status(400).json({ error: 'Domaine manquant ou invalide' });
    }

    const normalizedDomain = normalizeDomain(domain);
    if (!validateDomain(normalizedDomain)) {
      return res.status(400).json({ error: 'Format de domaine invalide' });
    }

    if (source === 'scout' && searchId) {
      return res.status(400).json({ error: 'search_id est incompatible avec source=scout' });
    }

    let displayNameSource = null;
    let scoutRow = null;
    let resolved = null;

    try {
      if (source === 'scout') {
        try {
          scoutRow = await findScoutAgencyByDomain(normalizedDomain);
        } catch (err) {
          console.error('[POST /agencies/target] Agency Scout indisponible:', err.message);
          return res.status(500).json({ error: `Agency Scout indisponible : ${err.message}` });
        }
        if (!scoutRow) {
          return res.status(404).json({
            error: `Domaine ${normalizedDomain} absent de la base Agency Scout — relance un scan ou vérifie le domaine`
          });
        }
        displayNameSource = scoutRow.name;
      } else {
        try {
          // Charger la recherche demandée (repli contrôlé sur latest.json)
          resolved = readSearchPayload(searchId);
        } catch (err) {
          return res.status(404).json({ error: err.message });
        }

        const agencies = resolved.payload.agencies || [];

        // Trouver l'agence
        const agency = agencies.find(a => domainMatchesAgency(normalizedDomain, a));
        if (!agency) {
          return res.status(404).json({
            error: `Agence avec domaine ${normalizedDomain} non trouvée dans la recherche « ${resolved.search_id} »`
          });
        }
        displayNameSource = agency.name;
      }

      // Vérifier idempotence
      const csvPath = path.join(PROJECT_ROOT, 'config/companies.csv');
      const yamlPath = path.join(PROJECT_ROOT, 'config/companies.yaml');
      // Nom nettoyé : évite qu'un « Voir » scrapé pollue csv → mesure → lettre
      const displayName = cleanAgencyName(displayNameSource, normalizedDomain);
      const alreadyTargeted = isAlreadyTargeted(normalizedDomain, csvPath);

      if (!dry && !alreadyTargeted) {
        // Ajouter append-only. Le scout apporte une adresse Google vérifiée :
        // statut « retenue » + adresse/CP écrits dans le banc d'essai.
        const scoutOptions = scoutRow ? {
          statut: 'retenue',
          adresse: scoutRow.address || '',
          codePostal: (String(scoutRow.address || '').match(/\b(\d{5})\b/) || [])[1] || '',
          // URL relevée par le scout (avec www) : ne pas la reconstruire depuis
          // le domaine normalisé, un certificat TLS peut ne couvrir que www.
          site: scoutRow.website || '',
          // Catégorie du scout (agence | formation | autre) : une organisme de
          // formation entre au banc avec son type réel, sinon poste_vise_par_type
          // la traite comme une agence et les textes partent en angle « dev ».
          type: scoutRow.categorie === 'formation' ? 'formation_organisation' : 'agence_com_engagee',
        } : undefined;
        appendToCSV(csvPath, displayName, normalizedDomain, scoutOptions);
        appendToYAML(yamlPath, displayName, normalizedDomain, scoutOptions);
        console.log(`[POST /agencies/target] Agence ${displayName} ajoutée au ciblage (source: ${source})`);
        // Préparer une candidature, c'est retenir. L'inverse — une fiche
        // préparée qui resterait « à décider » — se relirait comme un oubli.
        try { writeDecision(normalizedDomain, 'retenu', 'preparation'); }
        catch (err) { console.error('[POST /agencies/target] décision non écrite:', err.message); }
      }

      if (dry) {
        return res.json({
          ok: true,
          domain: normalizedDomain,
          dry: true,
          already_targeted: alreadyTargeted,
          agency_name: displayName,
          source,
          instructions_chars: instructions.length,
          search_id: resolved ? resolved.search_id : null
        });
      }

      const task = enqueueAgencyTask({
        domain: normalizedDomain,
        agencyName: displayName,
        alreadyTargeted,
        instructions,
      });
      res.status(202).json({
        accepted: true,
        task_id: task.task_id,
        source,
        search_id: resolved ? resolved.search_id : null,
        status: publicAgencyTask(task),
      });
    } catch (err) {
      console.error('[POST /agencies/target]', err.message);
      res.status(500).json({ error: err.message });
    }
  });

  // GET /api/agencies/target/status/:taskId — Suit mesure, candidature et CV
  router.get('/agencies/target/status/:taskId', (req, res) => {
    const task = agencyTasks.get(req.params.taskId);
    if (!task) {
      return res.status(404).json({ error: 'Tâche agence introuvable ou expirée' });
    }
    res.json(publicAgencyTask(task));
  });

  return router;
}
