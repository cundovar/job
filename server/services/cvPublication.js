// Définition unique de « ce CV est-il publiable ». L'API, le catalogue et le
// front lisent tous cette fonction : c'est ce qui a fait disparaître les trois
// prédicats divergents qui cohabitaient auparavant.

// Fichiers réservés à un CV éditorialement validé.
export const FINAL_CV_FILES = [
  'cv_final.json',
  'cv_final.html',
  'cv_final.pdf',
  'cv_ats.html',
  'cv_ats.pdf',
];

// Artefacts produits quel que soit le verdict : ils servent au diagnostic.
export const DIAGNOSTIC_CV_FILES = [
  'cv_adaptation_plan.json',
  'cv_draft.json',
  'cv_review.json',
  'cv_truth_check.json',
  'cv_final_review.json',
  'cv_content.json',
  'cv_agent_trace.json',
  'cv_assessment.json',
];

// Aperçus d'un CV refusé, nommés pour ne pas être pris pour un CV validé.
export const PREVIEW_CV_FILES = [
  'cv_review_preview.html',
  'cv_review_preview.pdf',
  'cv_review_preview_ats.html',
  'cv_review_preview_ats.pdf',
];

export const CV_FILES = new Set([
  ...DIAGNOSTIC_CV_FILES,
  ...FINAL_CV_FILES,
  ...PREVIEW_CV_FILES,
]);

const FINAL_SET = new Set(FINAL_CV_FILES);

export function isFinalCvFile(file) {
  return FINAL_SET.has(file);
}

function reviewReason(review, formatIssues) {
  if (review?.status === 'needs_revision' || review?.status === 'needs_minor_revision') {
    return review.verdict || 'Le juge IA demande une correction.';
  }
  if (formatIssues.length) {
    return formatIssues[0].detail || 'Une contrainte de mise en page reste à corriger.';
  }
  return 'Le CV demande une vérification avant envoi.';
}

/**
 * Traduit l'état d'un dossier en statut de publication.
 *
 * `absent`  aucun CV généré — le CV reste optionnel, rien n'est bloqué ;
 * `review`  généré mais pas validé — pas de fichier final, envoi refusé ;
 * `blocked` un contrôle de vérité a échoué ;
 * `ready`   validé ET fichiers finaux présents.
 *
 * `preparing` n'apparaît pas ici : il vient de l'état de la tâche asynchrone,
 * pas de l'état du dossier sur disque.
 */
export function resolveCvPublication(files = {}, assessment = null, review = null) {
  const hasAnyFile = Object.values(files).some(Boolean);
  const finalFilesPresent = FINAL_CV_FILES.every(file => files[file]);

  if (!hasAnyFile) {
    return {
      status: 'absent',
      reason: "Aucun CV n'a encore été généré.",
      blocking_issues: [],
      format_issues: [],
      revision_rounds: null,
    };
  }

  const publication = assessment?.publication || null;
  const blockingIssues = Array.isArray(publication?.blocking_issues) ? publication.blocking_issues : [];
  const formatIssues = Array.isArray(publication?.format_issues) ? publication.format_issues : [];
  const revisionRounds = Number.isInteger(publication?.revision_rounds) ? publication.revision_rounds : null;
  const base = {
    blocking_issues: blockingIssues,
    format_issues: formatIssues,
    revision_rounds: revisionRounds,
  };

  // Lecture prudente d'un dossier antérieur au contrat de publication : sans
  // évaluation lisible, on ne déclare jamais un CV prêt.
  if (!assessment || typeof assessment.overall_status !== 'string') {
    return {
      status: 'review',
      reason: finalFilesPresent
        ? 'Dossier antérieur au contrat de publication : évaluation à refaire.'
        : 'Évaluation du CV illisible ou absente.',
      ...base,
    };
  }

  if (assessment.overall_status === 'blocked') {
    return {
      status: 'blocked',
      reason: blockingIssues[0]?.detail || 'Un contrôle de vérité a échoué.',
      ...base,
    };
  }
  if (assessment.overall_status !== 'ready') {
    return { status: 'review', reason: reviewReason(review, formatIssues), ...base };
  }
  if (!finalFilesPresent) {
    // L'évaluation dit « prêt » mais les fichiers finaux manquent : on ne
    // propose pas au téléchargement ce qui n'existe pas.
    return {
      status: 'review',
      reason: 'Les fichiers finaux du CV sont absents ou incomplets.',
      ...base,
    };
  }
  return { status: 'ready', reason: null, ...base };
}
