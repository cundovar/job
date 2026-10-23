/**
 * services/jobOffer.js — L'annonce d'une candidature, telle que la chaîne CV
 * et lettre l'a lue.
 *
 * Source par ordre de fidélité :
 *   1. job.json : la description complète, celle qu'ont lue les agents ;
 *   2. offre_resume.md (section « Description courte ») pour les dossiers
 *      d'avant job.json, avec metadata.json pour le titre et le lien.
 * Une annonce absente se dit (`available: false`), elle n'est jamais
 * reconstituée : ce panneau sert à relire ce qui a été envoyé aux agents.
 */
import fs from 'fs';
import path from 'path';

const MAX_DESCRIPTION = 60_000;

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf-8'));
  } catch {
    return null;
  }
}

function text(value) {
  return typeof value === 'string' ? value.trim() : '';
}

/** Texte de la section « ## Description courte » d'un offre_resume.md. */
function resumeDescription(markdown) {
  const match = /^##\s+Description courte\s*$/im.exec(markdown || '');
  if (!match) return '';
  const rest = markdown.slice(match.index + match[0].length);
  const next = /^##\s+/m.exec(rest);
  return (next ? rest.slice(0, next.index) : rest).trim();
}

function readJobOffer(dir) {
  const job = readJson(path.join(dir, 'job.json'));
  const metadata = readJson(path.join(dir, 'metadata.json')) || {};
  let description = text(job?.description);
  let source = description ? 'job.json' : '';
  if (!description) {
    try {
      description = resumeDescription(fs.readFileSync(path.join(dir, 'offre_resume.md'), 'utf-8'));
      if (description) source = 'offre_resume.md';
    } catch {
      // pas de résumé : l'annonce n'a pas été conservée
    }
  }
  const truncated = description.length > MAX_DESCRIPTION;
  return {
    available: Boolean(description),
    source,
    title: text(job?.title) || text(metadata.job_title),
    company: text(job?.company) || text(metadata.company),
    location: text(job?.location),
    contract_type: text(job?.contract_type),
    url: text(job?.url) || text(metadata.url),
    description: truncated ? description.slice(0, MAX_DESCRIPTION) : description,
    truncated,
  };
}

export { readJobOffer, resumeDescription };
