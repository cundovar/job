import path from 'path';

const CV_DOWNLOAD_VARIANTS = {
  'cv_final.pdf': 'design',
  'cv_ats.pdf': 'ATS',
  'cv_final.html': 'design',
  'cv_ats.html': 'ATS',
  'cv_final.json': 'données',
  'cv_assessment.json': 'évaluation',
  'cv_review.json': 'contrôle',
  'cv_final_review.json': 'contrôle-final',
  'cv_draft.json': 'brouillon',
  'cv_adaptation_plan.json': 'plan-adaptation',
  'cv_agent_trace.json': 'trace',
};

function filenamePart(value, fallback) {
  const normalized = String(value || '')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-zA-Z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return normalized || fallback;
}

export function downloadFilename(application, file) {
  const candidate = filenamePart(process.env.CV_CANDIDATE_NAME || 'Facundo Varas', 'Candidat');
  const company = filenamePart(application?.entreprise, 'Entreprise');
  const role = filenamePart(application?.poste, 'Poste');
  const extension = path.extname(file) || '.bin';
  const variant = filenamePart(CV_DOWNLOAD_VARIANTS[file] || path.basename(file, extension), 'CV');
  return `CV_${candidate}_${company}_${role}_${variant}${extension}`;
}
