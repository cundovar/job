import path from 'path';

const CV_DOWNLOAD_VARIANTS = {
  'cv_final.pdf': '',
  'cv_ats.pdf': 'ATS',
  'cv_final.html': 'HTML',
  'cv_ats.html': 'ATS-HTML',
  'cv_final.json': 'données',
  'cv_assessment.json': 'évaluation',
  'cv_review.json': 'contrôle',
  'cv_final_review.json': 'contrôle-final',
  'cv_draft.json': 'brouillon',
  'cv_adaptation_plan.json': 'plan-adaptation',
  'cv_agent_trace.json': 'trace',
};

function filenamePart(value, fallback, maxLength) {
  const normalized = String(value || '')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-zA-Z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  const safeValue = normalized || fallback;
  if (!maxLength || safeValue.length <= maxLength) return safeValue;

  const clipped = safeValue.slice(0, maxLength + 1);
  const wordBoundary = clipped.lastIndexOf('-');
  return (wordBoundary >= Math.floor(maxLength * 0.6)
    ? clipped.slice(0, wordBoundary)
    : safeValue.slice(0, maxLength)
  ).replace(/-+$/g, '');
}

function roleFilenamePart(value) {
  const normalized = filenamePart(value, 'Poste')
    .replace(/^(?:charge-e?|chargee?|responsable|coordinateur|coordinatrice)-(?:d-)?(?:de|du|des)-/i, '')
    .split('-')
    .filter((part) => !['d', 'de', 'du', 'des', 'et', 'pour', 'le', 'la', 'les', 'un', 'une'].includes(part.toLowerCase()))
    .join('-');
  const shortened = filenamePart(normalized, 'Poste', 36);
  return shortened.charAt(0).toUpperCase() + shortened.slice(1);
}

export function downloadFilename(application, file) {
  const candidate = filenamePart(process.env.CV_CANDIDATE_NAME || 'Facundo Varas', 'Candidat');
  const company = filenamePart(application?.entreprise, 'Entreprise', 25);
  const role = roleFilenamePart(application?.poste);
  const extension = path.extname(file) || '.bin';
  const configuredVariant = CV_DOWNLOAD_VARIANTS[file];
  const variant = configuredVariant === ''
    ? ''
    : filenamePart(configuredVariant || path.basename(file, extension), 'CV');
  const basename = ['CV', candidate, company, role, variant].filter(Boolean).join('_');
  return `${basename}${extension}`;
}
