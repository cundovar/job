/**
 * index.js — Point d'entrée du serveur Express.
 *
 * POUR CHANGER DE REPOSITORY (ex: passer à PostgreSQL) :
 *   1. Crée sqlApplicationsRepository.js implémentant la même interface
 *   2. Remplace la ligne d'import ci-dessous — c'est TOUT.
 */

import express from 'express';
import cors from 'cors';
import fs from 'fs';
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

// /data est ecrit a l'execution (pipeline Python / volume Coolify), pas au
// build : Vite ne copie public/ dans dist/ qu'a la construction de l'image,
// donc on sert ce dossier separement pour toujours refleter le contenu live.
const frontDataPath = path.resolve(__dirname, '../front/public/data');

// Sélection locale permanente : petites agences web/digitales proches de
// 21 rue Monte-Cristo / Nation, pertinentes pour WordPress, intégrations,
// automatisation n8n/APIs et développement web polyvalent.
const CURATED_AGENCIES = [
  {
    name: 'WEBDIGITAL',
    website: 'https://www.webdigital.fr/',
    score: 95,
    stack: ['WordPress', 'Développement web', 'UX/UI', 'SEO', 'Stratégie digitale'],
    emails: ['candidature@webdigital.fr'],
    contact_urls: ['https://www.webdigital.fr/contact/'],
    query: 'Paris 20e · candidature spontanée prioritaire',
    reasons: [
      'Adresse : 6 Villa du Borrégo, Paris 20e.',
      'Priorité 1 : excellente cible locale pour un profil web polyvalent.',
      'Création/refonte de sites, développement web, UX/UI, SEO et stratégie digitale.',
      'Angle conseillé : WordPress + JavaScript + APIs + automatisation n8n.',
      'Une adresse email dédiée aux candidatures est disponible.'
    ]
  },
  {
    name: 'Bew Web Agency',
    website: 'https://www.bew-web-agency.fr/',
    score: 93,
    stack: ['WordPress', 'Maintenance', 'Hébergement', 'SEO', 'Création de sites'],
    emails: [],
    contact_urls: ['https://www.bew-web-agency.fr/contact/'],
    query: 'Paris 20e · WordPress prioritaire',
    reasons: [
      'Adresse : 401 rue des Pyrénées, Paris 20e.',
      'Priorité 2 : très bonne adéquation avec WordPress et la maintenance web.',
      'Ton expérience WordPress/WooCommerce et intégration front est directement pertinente.',
      'Mettre en avant les APIs et n8n comme compétence complémentaire différenciante.',
      'Bonne cible pour une candidature spontanée de développeur web polyvalent.'
    ]
  },
  {
    name: 'YOTTA',
    website: 'https://www.yotta-agency.com/',
    score: 89,
    stack: ['Web', 'Stratégie digitale', 'Contenu', 'Vidéo'],
    emails: [],
    contact_urls: ['https://www.yotta-agency.com/contact/'],
    query: 'Paris 20e · web + digital',
    reasons: [
      'Adresse : 10 rue Désirée, Paris 20e.',
      'Priorité 3 : agence locale plus structurée avec une activité web réelle.',
      'Présenter le profil comme Développeur web — automatisation & intégrations.',
      'Mettre en avant WordPress, JavaScript, APIs, n8n et IA plutôt qu’un positionnement WordPress seul.',
      'Candidature spontanée pertinente même hors offre publiée.'
    ]
  },
  {
    name: 'OFA Web',
    score: 82,
    stack: ['Agence web', 'Création de sites'],
    emails: [],
    contact_urls: [],
    query: 'Paris 20e · petite agence locale',
    reasons: [
      'Adresse : 5 square Got, Paris 20e.',
      'Priorité 4 : petite structure locale à prospecter directement.',
      'Profil polyvalent intéressant pour des besoins mêlant site, intégration et petites automatisations.',
      'Conseil : candidature courte avec CV, portfolio et mention de la proximité géographique.',
      'À vérifier : stack et besoins actuels avant l’envoi.'
    ]
  },
  {
    name: 'Yes Digital',
    score: 78,
    stack: ['Agence digitale', 'Web'],
    emails: [],
    contact_urls: [],
    query: 'Paris 20e · prospection locale',
    reasons: [
      'Adresse : 24 rue de l’Est, Paris 20e.',
      'Priorité 5 : agence locale intéressante à prospecter.',
      'Ton profil peut convenir si l’agence gère des sites, intégrations ou projets digitaux sur mesure.',
      'Mettre en avant la polyvalence WordPress + APIs + automatisation.',
      'Vérifier l’activité récente et l’équipe avant l’envoi.'
    ]
  },
  {
    name: 'Agence Cassian',
    score: 76,
    stack: ['Agence digitale', 'Web', 'Communication'],
    emails: [],
    contact_urls: [],
    query: 'Nation / Paris 11e · proche du 20e',
    reasons: [
      'Adresse : 103 boulevard de Charonne, Paris 11e.',
      'Priorité 6 : juste à côté du secteur Nation / Paris 20e.',
      'À cibler si l’agence produit ou maintient des sites pour ses clients.',
      'Angle conseillé : développeur web polyvalent + automatisation des tâches internes/client.',
      'Bonne cible dans une prospection élargie autour de chez toi.'
    ]
  },
  {
    name: 'd-story',
    score: 72,
    stack: ['Communication', 'Publicité', 'Digital'],
    emails: [],
    contact_urls: [],
    query: 'Paris 20e · communication digitale',
    reasons: [
      'Adresse : 17 rue Pelleport, Paris 20e.',
      'Priorité 7 : plus orientée communication/publicité que développement pur.',
      'Intéressante surtout si elle produit des sites, landing pages ou dispositifs digitaux pour ses clients.',
      'Mettre l’accent sur WordPress, intégration et automatisations simples.',
      'Moins prioritaire que WEBDIGITAL, Bew Web Agency ou YOTTA.'
    ]
  }
];

function seedCuratedAgencies() {
  try {
    const agenciesDir = path.join(frontDataPath, 'agencies');
    const agenciesFile = path.join(agenciesDir, 'latest.json');
    fs.mkdirSync(agenciesDir, { recursive: true });

    let existing = { agencies: [] };
    if (fs.existsSync(agenciesFile)) {
      try {
        existing = JSON.parse(fs.readFileSync(agenciesFile, 'utf8'));
      } catch {
        existing = { agencies: [] };
      }
    }

    const discovered = Array.isArray(existing.agencies) ? existing.agencies : [];
    const curatedNames = new Set(CURATED_AGENCIES.map(a => a.name.toLowerCase()));
    const withoutDuplicates = discovered.filter(
      agency => !curatedNames.has(String(agency?.name || '').toLowerCase())
    );

    const merged = {
      ...existing,
      generated_at: new Date().toISOString(),
      curated_for: '21 rue Monte-Cristo, Paris 20e / Nation',
      agencies: [...CURATED_AGENCIES, ...withoutDuplicates]
    };

    fs.writeFileSync(agenciesFile, `${JSON.stringify(merged, null, 2)}\n`, 'utf8');
    console.log(`🏢 Agences locales : ${CURATED_AGENCIES.length} cibles permanentes ajoutées`);
  } catch (error) {
    console.warn('⚠️ Impossible de fusionner les agences locales :', error.message);
  }
}

seedCuratedAgencies();
app.use('/data', express.static(frontDataPath));

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
  console.log(`   GET  /api/applications/prepare/status/:taskId`);
  console.log(`   POST /api/applications/:id/cv/prepare`);
  console.log(`   GET  /api/applications/:id/cv/status`);
  console.log(`   GET  /api/applications/:id/cv/download/:file`);
  console.log(`   POST /api/applications/:id/applied`);
  console.log(`   POST /api/applications/:id/not-applied`);
  console.log(`   POST /api/search/run`);
  console.log(`   GET  /api/search/status`);
});