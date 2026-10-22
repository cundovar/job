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
  'cv_progress.json',
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

// CV fourni par le candidat depuis l'onglet lettre (demande Cundo 21/10/2026).
// Il remplace le CV généré, ou en tient lieu quand aucun CV n'a été demandé :
// c'est lui qui part à l'envoi, quel que soit le verdict du pipeline.
export const UPLOADED_CV_PDF = 'cv_upload.pdf';

// Version du CV modifiée par le candidat dans l'éditeur (demande Cundo
// 22/10/2026), produite par `python -m cv_generator.user_edit` : sa parole,
// pas une affirmation de l'IA. Elle remplace le CV généré à l'envoi.
export const EDITED_CV_JSON = 'cv_edit.json';
export const EDITED_CV_PDF = 'cv_edit.pdf';
export const EDITED_CV_ATS_PDF = 'cv_edit_ats.pdf';

export const CV_FILES = new Set([
  ...DIAGNOSTIC_CV_FILES,
  ...FINAL_CV_FILES,
  ...PREVIEW_CV_FILES,
  UPLOADED_CV_PDF,
  EDITED_CV_JSON,
  EDITED_CV_PDF,
  EDITED_CV_ATS_PDF,
]);

const FINAL_SET = new Set(FINAL_CV_FILES);

// Validation humaine d'un CV que l'IA a laissé « à corriger ». Elle porte
// l'empreinte de l'aperçu validé : un CV régénéré n'hérite jamais d'un accord
// donné à un autre contenu.
export const USER_VALIDATION_FILE = 'cv_user_validation.json';
export const USER_VALIDATED_PDF = 'cv_review_preview.pdf';

export function isFinalCvFile(file) {
  return FINAL_SET.has(file);
}

function reviewReason(review, formatIssues, sourceIssues) {
  // Une source incomplète passe devant : aucune relecture éditoriale ne la
  // réparera, c'est le profil maître qu'il faut compléter.
  if (sourceIssues.length) {
    return sourceIssues[0].detail || 'Le profil maître est incomplet sur une date.';
  }
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
 * `absent`    aucun CV généré — le CV reste optionnel, rien n'est bloqué ;
 * `review`    généré mais pas validé — pas de fichier final, envoi refusé ;
 * `validated` un `review` que l'utilisateur a relu et accepté tel quel : il
 *             tranche là où l'IA hésitait (règle 3). L'aperçu devient le CV
 *             envoyé ; aucun fichier `cv_final` n'est fabriqué pour autant ;
 * `blocked`   un contrôle de vérité a échoué — jamais validable à la main :
 *             la preuve manque dans le profil maître (règle 2) ;
 * `ready`     validé ET fichiers finaux présents ;
 * `edited`    le candidat a réécrit le CV dans l'éditeur : sa version part,
 *             comme un PDF qu'il ajoute (`uploaded`, prioritaire sur tout).
 *
 * `preparing` n'apparaît pas ici : il vient de l'état de la tâche asynchrone,
 * pas de l'état du dossier sur disque.
 */
export function resolveCvPublication(files = {}, assessment = null, review = null, userValidation = null) {
  if (files[UPLOADED_CV_PDF]) {
    const generated = resolveAutomaticPublication({ ...files, [UPLOADED_CV_PDF]: false }, assessment, review);
    return {
      ...generated,
      status: 'uploaded',
      reason: 'CV ajouté par toi : il remplace le CV généré à l\u2019envoi.',
      generated_status: generated.status,
    };
  }
  if (files[EDITED_CV_PDF] && files[EDITED_CV_JSON]) {
    const generated = resolveAutomaticPublication(files, assessment, review);
    return {
      ...generated,
      status: 'edited',
      reason: 'Version modifiée par toi : elle remplace le CV généré à l\u2019envoi.',
      generated_status: generated.status,
    };
  }
  const publication = resolveAutomaticPublication(files, assessment, review);
  if (publication.status === 'review' && userValidation?.valid && files[USER_VALIDATED_PDF]) {
    return {
      ...publication,
      status: 'validated',
      user_validation: {
        validated_at: userValidation.validated_at || null,
        ai_reason: userValidation.ai_reason || publication.reason,
      },
    };
  }
  return publication;
}

function resolveAutomaticPublication(files = {}, assessment = null, review = null) {
  const hasAnyFile = Object.values(files).some(Boolean);
  const finalFilesPresent = FINAL_CV_FILES.every(file => files[file]);

  if (!hasAnyFile) {
    return {
      status: 'absent',
      reason: "Aucun CV n'a encore été généré.",
      blocking_issues: [],
      format_issues: [],
      source_issues: [],
      revision_rounds: null,
    };
  }

  const publication = assessment?.publication || null;
  const blockingIssues = Array.isArray(publication?.blocking_issues) ? publication.blocking_issues : [];
  const formatIssues = Array.isArray(publication?.format_issues) ? publication.format_issues : [];
  const sourceIssues = Array.isArray(publication?.source_issues) ? publication.source_issues : [];
  const revisionRounds = Number.isInteger(publication?.revision_rounds) ? publication.revision_rounds : null;
  const base = {
    blocking_issues: blockingIssues,
    format_issues: formatIssues,
    source_issues: sourceIssues,
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
    return { status: 'review', reason: reviewReason(review, formatIssues, sourceIssues), ...base };
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
