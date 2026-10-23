import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { readJobOffer, resumeDescription } from './jobOffer.js';

function dossier(files) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'offre-'));
  for (const [name, content] of Object.entries(files)) {
    fs.writeFileSync(path.join(dir, name), typeof content === 'string' ? content : JSON.stringify(content));
  }
  return dir;
}

test("l'annonce complète vient de job.json", () => {
  const dir = dossier({
    'job.json': { title: 'Formateur', company: 'Simplon', url: 'https://x.test/1', description: 'Texte complet.\nMissions.' },
    'offre_resume.md': '## Description courte\n\nTexte court.',
  });
  const offre = readJobOffer(dir);
  assert.equal(offre.available, true);
  assert.equal(offre.source, 'job.json');
  assert.equal(offre.description, 'Texte complet.\nMissions.');
  assert.equal(offre.company, 'Simplon');
});

test('ancien dossier : description courte du résumé, titre et lien de metadata', () => {
  const dir = dossier({
    'metadata.json': { job_title: 'Gestionnaire applicatif', company: 'ROLESCO', url: 'https://ft.test/2' },
    'offre_resume.md': '# Resume\n\n## CV conseille\n\nx\n\n## Description courte\n\nLe poste.\nLes missions.\n',
  });
  const offre = readJobOffer(dir);
  assert.equal(offre.source, 'offre_resume.md');
  assert.equal(offre.description, 'Le poste.\nLes missions.');
  assert.equal(offre.title, 'Gestionnaire applicatif');
  assert.equal(offre.url, 'https://ft.test/2');
});

test("annonce non conservée : dit absente, rien d'inventé", () => {
  const offre = readJobOffer(dossier({ 'metadata.json': { job_title: 'Dev' } }));
  assert.equal(offre.available, false);
  assert.equal(offre.description, '');
});

test('la section suivante ne déborde pas dans la description', () => {
  assert.equal(resumeDescription('## Description courte\nA\n## Autre\nB'), 'A');
});
