/**
 * Agency Scout — deux routes, pas de file de tâches.
 *   GET  /api/scout/agencies  → lit data/agency_scout.db (via `python3 -m agency_scout list`)
 *   POST /api/scout/scan      → lance un scan détaché et rend la main ; le front relit GET.
 */
import { Router } from 'express';
import { execFile } from 'child_process';
import { PROJECT_ROOT } from '../config.js';

const PYTHON_BIN = process.env.PYTHON_BIN || 'python3';

function runScout(args, timeout = 20000) {
  return new Promise((resolve, reject) => {
    execFile(PYTHON_BIN, ['-m', 'agency_scout', ...args], { cwd: PROJECT_ROOT, timeout, maxBuffer: 20 * 1024 * 1024 },
      (err, stdout, stderr) => {
        if (err) return reject(new Error((stderr || err.message).slice(-500)));
        try { resolve(JSON.parse(stdout)); } catch { reject(new Error(`Réponse illisible : ${stdout.slice(0, 200)}`)); }
      });
  });
}

export function createScoutRouter() {
  const router = Router();

  router.get('/agencies', async (req, res) => {
    const args = ['list'];
    if (req.query.categorie) args.push('--categorie', String(req.query.categorie));
    if (req.query.min_score) args.push('--min-score', String(parseInt(req.query.min_score, 10) || 0));
    try { res.json(await runScout(args)); } catch (e) { res.status(500).json({ error: e.message }); }
  });

  router.post('/scan', async (req, res) => {
    const { lat, lng, rayon, reanalyse, cp } = req.body || {};
    const args = ['scan', '--background'];
    if (Number.isFinite(lat) && Number.isFinite(lng)) args.push('--lat', String(lat), '--lng', String(lng));
    if (Number.isFinite(rayon)) args.push('--rayon', String(Math.min(Math.max(rayon, 200), 50000)));
    const cps = Array.isArray(cp) ? cp : (cp ? String(cp).split(',') : []);
    for (const c of cps) {
      const t = String(c).trim();
      if (t) args.push('--cp', t); // mode arrondissement : le CP décide, le rayon ne filtre plus
    }
    if (reanalyse) args.push('--reanalyse');
    try { res.status(202).json(await runScout(args)); } catch (e) { res.status(500).json({ error: e.message }); }
  });

  return router;
}
