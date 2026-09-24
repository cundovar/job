/**
 * Agency Scout — trois routes, pas de file de tâches.
 *   GET  /api/scout/agencies  → lit data/agency_scout.db (via `python3 -m agency_scout list`)
 *   POST /api/scout/scan      → lance un scan détaché et rend la main ; le front relit GET.
 *   POST /api/scout/add       → ajoute une structure repérée à la main, depuis l'URL de son site.
 */
import { Router } from 'express';
import { execFile } from 'child_process';
import { PROJECT_ROOT } from '../config.js';

const PYTHON_BIN = process.env.PYTHON_BIN || 'python3';

function runScout(args, timeout = 20000) {
  return new Promise((resolve, reject) => {
    execFile(PYTHON_BIN, ['-m', 'agency_scout', ...args], { cwd: PROJECT_ROOT, timeout, maxBuffer: 20 * 1024 * 1024 },
      (err, stdout, stderr) => {
        let payload = null;
        try { payload = JSON.parse(stdout); } catch { /* sortie non JSON */ }
        if (err) {
          const error = new Error(payload?.error || (stderr || err.message).slice(-500));
          error.payload = payload;
          return reject(error);
        }
        if (payload) return resolve(payload);
        reject(new Error(`Réponse illisible : ${stdout.slice(0, 200)}`));
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

  // Le champ de périmètre accepte les deux écritures qu'on a en tête en le
  // remplissant : « 75020 » et « Nanterre ». Cinq chiffres = code postal ;
  // tout le reste est une commune, résolue par le CLI chez geo.api.gouv.fr —
  // qui en tire aussi le **centre** de recherche, sans quoi un code postal de
  // Nanterre cherché autour de Paris 20e ne rend rien et ne le dit pas.
  router.post('/scan', async (req, res) => {
    const { lat, lng, rayon, reanalyse, cp, ville, departement } = req.body || {};
    const args = ['scan', '--background'];
    const saisies = (Array.isArray(cp) ? cp : (cp ? String(cp).split(',') : []))
      .map(value => String(value).trim()).filter(Boolean);
    const codes = saisies.filter(value => /^\d{5}$/.test(value));
    const communes = saisies.filter(value => !/^\d{5}$/.test(value));
    const commune = String(ville || '').trim() || communes[0] || '';
    if (commune && codes.length) {
      return res.status(400).json({ error: `Choisis un périmètre : la commune « ${commune} » ou les codes postaux ${codes.join(', ')}, pas les deux.` });
    }
    if (communes.length > 1) {
      return res.status(400).json({ error: `Une seule commune par scan : ${communes.join(', ')}.` });
    }
    // Le centre n'accompagne que le mode rayon : en mode commune il vient de
    // la résolution, et le poser ici le contredirait.
    if (!commune && Number.isFinite(lat) && Number.isFinite(lng)) args.push('--lat', String(lat), '--lng', String(lng));
    if (Number.isFinite(rayon)) args.push('--rayon', String(Math.min(Math.max(rayon, 200), 50000)));
    if (commune) {
      args.push('--ville', commune);
      if (departement) args.push('--departement', String(departement).trim());
    }
    for (const code of codes) args.push('--cp', code); // le CP décide, le rayon ne filtre plus
    if (reanalyse) args.push('--reanalyse');
    // 60 s : la résolution de commune est un appel réseau, fait avant de rendre la main.
    try { res.status(202).json(await runScout(args, 60000)); } catch (e) { res.status(400).json({ error: e.message }); }
  });

  // Ajout manuel : une structure, un site, une analyse. Synchrone — un fetch
  // et un appel IA, de l'ordre de dix secondes : une file de tâches serait
  // plus de machinerie que de service. L'URL passe en argument d'execFile,
  // jamais par un shell ; le reste des refus vient du CLI, qui connaît les
  // hôtes qu'il s'interdit d'aller chercher.
  router.post('/add', async (req, res) => {
    const url = String(req.body?.url || '').trim();
    const nom = String(req.body?.nom || '').trim();
    if (!url) return res.status(400).json({ error: 'URL manquante.' });
    if (!/^(https?:\/\/)?[^\s/$.?#][^\s]*\.[^\s]{2,}$/i.test(url)) {
      return res.status(400).json({ error: `URL invalide : ${url}` });
    }
    const args = ['add', '--url', url];
    if (nom) args.push('--nom', nom);
    if (req.body?.reanalyse) args.push('--reanalyse');
    try {
      res.json(await runScout(args, 90000));
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  });

  return router;
}
