/**
 * routes/hermes.js — Proxy vers l'API de chat de l'agent Hermes.
 *
 * La clé HERMES_API_KEY reste côté serveur : le front ne voit jamais que
 * `sessionId` et `content`.
 */
import { Router } from 'express';

const CHAT_TIMEOUT_MS = 180000;
const DEFAULT_TIMEOUT_MS = 20000;
const RUN_MAX_AGE_MS = 20 * 60 * 1000; // au-dela, on considere le run comme abandonne (auto-guerison)

// Une seule recherche lancee depuis le chat a la fois (etat en memoire, cote app).
let searchRunState = { running: false, runId: null, searchId: null, startedAt: null };

function normalizeRunStatus(status) {
  if (status === 'completed') return 'done';
  if (status === 'failed' || status === 'cancelled') return 'failed';
  return 'running'; // started, running, queued, in_progress, ...
}

function buildSearchRunInstruction(message, searchId) {
  return [
    "[Consigne systeme - lancement de recherche demande EXPLICITEMENT par l'utilisateur depuis le chat de l'application. Ce n'est pas une initiative spontanee de ta part : n'utilise cette consigne que parce qu'elle t'est donnee maintenant.]",
    '',
    `Demande de l'utilisateur : ${message}`,
    '',
    `Lance la recherche d'emploi du jour avec l'outil job_today, en lui passant obligatoirement search_id="${searchId}" (cela archive ce run comme une session distincte, sans ecraser la recherche du jour).`,
    "Tiens compte des criteres eventuellement precises par l'utilisateur ci-dessus, sans jamais affaiblir les garde-fous existants (verite du profil, filtres).",
    "Une fois la recherche terminee, conclus ta reponse par un compte rendu court et chiffre : nombre d'offres trouvees, combien a POSTULER, combien en PEUT-ETRE. Ne detaille pas les offres une par une.",
  ].join('\n');
}

function hermesConfig() {
  const baseUrl = process.env.HERMES_API_URL;
  const apiKey = process.env.HERMES_API_KEY;
  if (!baseUrl || !apiKey) {
    throw new Error("HERMES_API_URL ou HERMES_API_KEY manquant dans l'environnement");
  }
  return { baseUrl, apiKey };
}

async function hermesFetch(pathSuffix, { method = 'GET', body, timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
  const { baseUrl, apiKey } = hermesConfig();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${baseUrl}${pathSuffix}`, {
      method,
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    const text = await response.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = null;
    }
    if (!response.ok) {
      const error = new Error(data?.error || `Hermes a répondu ${response.status}`);
      error.hermesStatus = response.status;
      throw error;
    }
    return data;
  } finally {
    clearTimeout(timer);
  }
}

async function createHermesSession() {
  const data = await hermesFetch('/api/sessions', { method: 'POST', body: {} });
  const sessionId = data?.session?.id;
  if (!sessionId) {
    throw new Error('Réponse Hermes invalide : session sans identifiant');
  }
  return sessionId;
}

export default function createHermesRouter() {
  const router = Router();

  // POST /api/hermes/session — crée une nouvelle session Hermes
  router.post('/session', async (_req, res) => {
    try {
      const sessionId = await createHermesSession();
      res.json({ sessionId });
    } catch (err) {
      console.error('[POST /hermes/session]', err.message);
      res.status(err.hermesStatus || 502).json({ error: err.message });
    }
  });

  // GET /api/hermes/messages/:sessionId — historique de la conversation
  router.get('/messages/:sessionId', async (req, res) => {
    try {
      const data = await hermesFetch(`/api/sessions/${encodeURIComponent(req.params.sessionId)}/messages`);
      const messages = Array.isArray(data?.data)
        ? data.data
            .filter(m => (m?.role === 'user' || m?.role === 'assistant')
              && typeof m.content === 'string' && m.content.trim() !== '')
            .map(m => ({ role: m.role, content: m.content }))
        : [];
      res.json({ messages });
    } catch (err) {
      console.error('[GET /hermes/messages]', err.message);
      res.status(err.hermesStatus || 502).json({ error: err.message });
    }
  });

  // POST /api/hermes/chat — envoie un message et attend la réponse de l'agent
  // (un tour d'agent peut prendre 30-120 s, timeout à 180 s côté proxy)
  router.post('/chat', async (req, res) => {
    try {
      const message = req.body?.message;
      if (!message || typeof message !== 'string') {
        return res.status(400).json({ error: 'Message invalide' });
      }
      let sessionId = req.body?.sessionId;
      if (!sessionId || typeof sessionId !== 'string') {
        sessionId = await createHermesSession();
      }
      const data = await hermesFetch(`/api/sessions/${encodeURIComponent(sessionId)}/chat`, {
        method: 'POST',
        body: { message },
        timeoutMs: CHAT_TIMEOUT_MS,
      });
      const content = data?.message?.content;
      if (typeof content !== 'string') {
        throw new Error('Réponse Hermes invalide : contenu manquant');
      }
      res.json({ sessionId, content });
    } catch (err) {
      const isTimeout = err.name === 'AbortError';
      const message = isTimeout ? "L'agent Hermes n'a pas répondu à temps" : err.message;
      console.error('[POST /hermes/chat]', message);
      res.status(err.hermesStatus || 502).json({ error: message });
    }
  });

  // Vrai si un run est toujours en cours ; se met a jour tout seul si le run
  // a fini entre-temps (auto-guerison, sans processus de fond dedie).
  async function isSearchStillRunning() {
    if (!searchRunState.running) return false;
    if (Date.now() - searchRunState.startedAt > RUN_MAX_AGE_MS) {
      searchRunState = { running: false, runId: null, searchId: null, startedAt: null };
      return false;
    }
    try {
      const data = await hermesFetch(`/v1/runs/${encodeURIComponent(searchRunState.runId)}`);
      if (normalizeRunStatus(data?.status) !== 'running') {
        searchRunState = { running: false, runId: null, searchId: null, startedAt: null };
        return false;
      }
      return true;
    } catch {
      // Etat Hermes indisponible : par prudence, on ne relance pas par-dessus un run existant.
      return true;
    }
  }

  // POST /api/hermes/search — lance une recherche d'emploi via Hermes (tache longue, /v1/runs)
  // Rend la main immediatement avec {runId, searchId} : ne pas attendre la fin du run ici,
  // c'est GET /search/:runId qui est sonde par le front.
  router.post('/search', async (req, res) => {
    try {
      const message = req.body?.message;
      if (!message || typeof message !== 'string') {
        return res.status(400).json({ error: 'Message invalide' });
      }
      if (await isSearchStillRunning()) {
        return res.status(409).json({
          error: 'Une recherche est deja en cours depuis le chat, attends sa fin avant d’en lancer une nouvelle.',
        });
      }
      const searchId = `chat-${Date.now()}`;
      const data = await hermesFetch('/v1/runs', {
        method: 'POST',
        body: { input: buildSearchRunInstruction(message, searchId) },
        timeoutMs: DEFAULT_TIMEOUT_MS,
      });
      const runId = data?.run_id;
      if (!runId) {
        throw new Error('Réponse Hermes invalide : run sans identifiant');
      }
      searchRunState = { running: true, runId, searchId, startedAt: Date.now() };
      res.json({ runId, searchId });
    } catch (err) {
      const isTimeout = err.name === 'AbortError';
      const message = isTimeout ? "Hermes n'a pas confirmé le lancement à temps" : err.message;
      console.error('[POST /hermes/search]', message);
      res.status(err.hermesStatus || 502).json({ error: message });
    }
  });

  // GET /api/hermes/search/:runId — état du run (statuts normalisés : running / done / failed)
  router.get('/search/:runId', async (req, res) => {
    try {
      const { runId } = req.params;
      const data = await hermesFetch(`/v1/runs/${encodeURIComponent(runId)}`);
      const status = normalizeRunStatus(data?.status);
      if (status !== 'running' && searchRunState.runId === runId) {
        searchRunState = { running: false, runId: null, searchId: null, startedAt: null };
      }
      const errorMessage = data?.error?.message || data?.error || null;
      res.json({
        status,
        output: typeof data?.output === 'string' ? data.output : null,
        error: status === 'failed' ? (errorMessage || 'La recherche a échoué.') : null,
      });
    } catch (err) {
      console.error('[GET /hermes/search/:runId]', err.message);
      res.status(err.hermesStatus || 502).json({ error: err.message });
    }
  });

  return router;
}
