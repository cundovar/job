/**
 * routes/hermes.js — Proxy vers l'API de chat de l'agent Hermes.
 *
 * La clé HERMES_API_KEY reste côté serveur : le front ne voit jamais que
 * `sessionId` et `content`.
 */
import { Router } from 'express';

const CHAT_TIMEOUT_MS = 180000;
const DEFAULT_TIMEOUT_MS = 20000;

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

  return router;
}
