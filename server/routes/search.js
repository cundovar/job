/**
 * routes/search.js — Déclenche le pipeline de recherche (identique au tool Hermes `job_today`)
 * depuis le front, et permet de suivre sa progression.
 */
import { Router } from 'express';
import { startSearch, getStatus } from '../services/searchRunner.js';

export default function createSearchRouter() {
  const router = Router();

  // POST /api/search/run — Démarre une recherche en arrière-plan (idempotent si déjà en cours)
  router.post('/run', (_req, res) => {
    const result = startSearch();
    res.status(result.alreadyRunning ? 200 : 202).json(result);
  });

  // GET /api/search/status — État courant (running, dernier résultat agrégé, etc.)
  router.get('/status', (_req, res) => {
    res.json(getStatus());
  });

  return router;
}
