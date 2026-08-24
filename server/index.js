/**
 * index.js — Point d'entrée du serveur Express.
 *
 * POUR CHANGER DE REPOSITORY (ex: passer à PostgreSQL) :
 *   1. Crée sqlApplicationsRepository.js implémentant la même interface
 *   2. Remplace la ligne d'import ci-dessous — c'est TOUT.
 */

import express from 'express';
import cors from 'cors';
import path from 'path';
import { fileURLToPath } from 'url';
import { PORT } from './config.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ── Repository actif (JSON sur disque) ────────────────────────────────────────
import JsonApplicationsRepository from './repositories/jsonApplicationsRepository.js';
// Pour passer à SQL plus tard : import SqlApplicationsRepository from './repositories/sqlApplicationsRepository.js'

import createApplicationsRouter from './routes/applications.js';
import createSearchRouter from './routes/search.js';

const app = express();

// CORS : en prod, accepte les requêtes du même origin (VPS)
const corsOrigin = process.env.NODE_ENV === 'production'
  ? '*'
  : 'http://localhost:5173';
app.use(cors({ origin: corsOrigin }));
app.use(express.json());

// Instancie le repository (une seule ligne à changer pour changer de stockage)
const repo = new JsonApplicationsRepository();

// Serve front statique depuis dist/ (production build)
const frontDistPath = path.resolve(__dirname, '../front/dist');
app.use(express.static(frontDistPath));

// Routes API
app.use('/api', createApplicationsRouter(repo));
app.use('/api/search', createSearchRouter());

// SPA fallback : redirige vers index.html pour les routes qui n'existent pas
app.get('*', (req, res) => {
  res.sendFile(path.join(frontDistPath, 'index.html'));
});

app.listen(PORT, () => {
  console.log(`✅ Serveur démarré sur http://localhost:${PORT}`);
  console.log(`📱 Frontend: http://localhost:${PORT}`);
  console.log(`📡 API:`);
  console.log(`   GET  /api/health`);
  console.log(`   GET  /api/applications`);
  console.log(`   POST /api/applications/prepare`);
  console.log(`   POST /api/applications/:id/applied`);
  console.log(`   POST /api/applications/:id/not-applied`);
  console.log(`   POST /api/search/run`);
  console.log(`   GET  /api/search/status`);
});
