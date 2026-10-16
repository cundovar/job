import path from 'path';

const CV_DOWNLOAD_VARIANTS = {
  'cv_final.pdf': '',
  'cv_ats.pdf': 'ATS',
  'cv_final.html': 'HTML',
  'cv_ats.html': 'ATS-HTML',
  'cv_final.json': 'données',
  'cv_assessment.json': 'évaluation',
  // Aperçus : même nommage que les fichiers finaux (décision Cundo, 2026-10-16 :
  // pas de marqueur « A-CORRIGER » dans le nom de téléchargement, même quand le
  // CV reste à corriger côté pipeline — le statut reste visible dans l'app).
  'cv_review_preview.pdf': '',
  'cv_review_preview.html': 'HTML',
  'cv_review_preview_ats.pdf': 'ATS',
  'cv_review_preview_ats.html': 'ATS-HTML',
  'cv_content.json': 'contenu',
  'cv_progress.json': 'progression',
  'cv_truth_check.json': 'controle-verite',
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
  // La lettre de motivation ne porte pas le préfixe « CV_ » (décision Cundo).
  const isLettre = /^lettre/i.test(path.basename(file));
  const configuredVariant = CV_DOWNLOAD_VARIANTS[file];
  const variant = configuredVariant === ''
    ? ''
    : filenamePart(configuredVariant || path.basename(file, extension), 'CV');
  const basename = [
    ...(isLettre ? [] : ['CV']),
    candidate,
    company,
    role,
    variant,
  ].filter(Boolean).join('_');
  return `${basename}${extension}`;
}
