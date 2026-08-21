/**
 * index.js — Point d'entrée du serveur Express.
 *
 * POUR CHANGER DE REPOSITORY (ex: passer à PostgreSQL) :
 *   1. Crée sqlApplicationsRepository.js implémentant la même interface
 *   2. Remplace la ligne d'import ci-dessous — c'est TOUT.
 */

import express from 'express';
import cors from 'cors';
import { PORT } from './config.js';

// ── Repository actif (JSON sur disque) ────────────────────────────────────────
import JsonApplicationsRepository from './repositories/jsonApplicationsRepository.js';
// Pour passer à SQL plus tard : import SqlApplicationsRepository from './repositories/sqlApplicationsRepository.js'

import createApplicationsRouter from './routes/applications.js';

const app = express();

// Autorise les requêtes depuis le frontend Vite (localhost:5173)
app.use(cors({ origin: 'http://localhost:5173' }));
app.use(express.json());

// Instancie le repository (une seule ligne à changer pour changer de stockage)
const repo = new JsonApplicationsRepository();

// Monte les routes sous /api
app.use('/api', createApplicationsRouter(repo));

app.listen(PORT, () => {
  console.log(`✅ Serveur démarré sur http://localhost:${PORT}`);
  console.log(`   GET  /api/health`);
  console.log(`   GET  /api/applications`);
  console.log(`   POST /api/applications/prepare`);
  console.log(`   POST /api/applications/:id/applied`);
  console.log(`   POST /api/applications/:id/not-applied`);
});
