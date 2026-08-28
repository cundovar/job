const CONTROL_LABELS = {
  eligibility: 'Éligibilité',
  parseability: 'Parsing',
  truthfulness: 'Véracité',
}

const STATUS_LABELS = {
  pass: 'Réussi',
  fail: 'Échec',
  review: 'À vérifier',
  ready: 'Prêt',
  blocked: 'Bloqué',
}

const REVIEW_STATUS_LABELS = {
  validated: 'Validé par le juge IA',
  needs_minor_revision: 'À vérifier',
  needs_revision: 'À corriger',
}

function Score({ label, value, band }) {
  return (
    <div className="cv-assessment-score">
      <span>{label}</span>
      <strong>{Number.isFinite(value) ? `${value}/100` : '—'}</strong>
      {band && <small>{band}</small>}
    </div>
  )
}

function LegacyAssessment({ review }) {
  if (!review) return null
  return (
    <section className="cv-assessment" aria-label="Ancienne évaluation du CV">
      <div className="cv-assessment-heading">
        <h3>Évaluation historique</h3>
        <span className="cv-assessment-status review">Ancien format</span>
      </div>
      <div className="cv-assessment-scores">
        <Score label="Qualité" value={review.quality_score} />
        <Score label="Ancien indicateur ATS" value={review.ats_score} />
      </div>
    </section>
  )
}

export default function CvAssessment({ assessment, legacyReview, finalReview }) {
  const review = finalReview || legacyReview
  if (!assessment) return <LegacyAssessment review={review} />
  const controls = ['eligibility', 'parseability', 'truthfulness']
  const displayedStatus = review?.status === 'needs_revision'
    ? 'review'
    : assessment.overall_status || 'review'
  const alerts = controls.flatMap(key => {
    const control = assessment[key] || {}
    const checkAlerts = (control.checks || [])
      .filter(item => item.status !== 'pass')
      .map(item => `${CONTROL_LABELS[key]} — ${item.requirement || item.id}: ${item.reason || 'à vérifier'}`)
    if (checkAlerts.length) return checkAlerts
    if (control.status !== 'pass' && control.reason) return [`${CONTROL_LABELS[key]} — ${control.reason}`]
    return []
  })

  return (
    <section className="cv-assessment" aria-label="Évaluation du CV">
      <div className="cv-assessment-heading">
        <div>
          <span className="manual-cv-kicker">Évaluation</span>
          <h3>Compatibilité de la candidature</h3>
        </div>
        <span className={`cv-assessment-status ${displayedStatus}`}>
          {review?.status === 'needs_revision'
            ? 'À corriger'
            : STATUS_LABELS[displayedStatus] || 'À vérifier'}
        </span>
      </div>
      <div className="cv-assessment-grid">
        <div className="cv-assessment-controls">
          {controls.map(key => {
            const status = assessment[key]?.status || 'review'
            return (
              <div className="cv-assessment-control" key={key}>
                <span>{CONTROL_LABELS[key]}</span>
                <strong className={status}>{STATUS_LABELS[status] || status}</strong>
              </div>
            )
          })}
        </div>
        <div className="cv-assessment-scores">
          <Score label="Correspondance" value={assessment.match?.score} band={assessment.match?.band} />
          <Score label="Qualité humaine" value={assessment.human_quality?.score} band={assessment.human_quality?.band} />
        </div>
      </div>
      {alerts.length > 0 && (
        <div className="cv-assessment-alerts">
          <strong>Points à vérifier</strong>
          <ul>{alerts.map(item => <li key={item}>{item}</li>)}</ul>
        </div>
      )}
      {review && (
        <details className="cv-ai-review" open={review.status === 'needs_revision'}>
          <summary>
            <span>Jugement détaillé des agents IA</span>
            <strong className={review.status || 'needs_minor_revision'}>
              {REVIEW_STATUS_LABELS[review.status] || 'À vérifier'}
            </strong>
          </summary>
          {review.agent_run && (
            <p className="cv-ai-review-agent">
              Juge : {review.agent_run.provider || 'IA'} · {review.agent_run.model || 'modèle non précisé'}
            </p>
          )}
          {review.verdict && <p className="cv-ai-review-verdict">{review.verdict}</p>}
          {(review.strengths || []).length > 0 && (
            <div className="cv-ai-review-strengths">
              <strong>Points solides relevés</strong>
              <ul>{review.strengths.map((item, index) => <li key={`strength-${index}`}>{item}</li>)}</ul>
            </div>
          )}
          {(review.problems || []).length > 0 && (
            <div className="cv-ai-review-problems">
              <strong>Pourquoi le CV doit être corrigé</strong>
              <ul>
                {review.problems.map((item, index) => (
                  <li key={`${item.section || 'general'}-${index}`}>
                    <strong>{item.section || 'Général'} :</strong> {item.problem}
                    {item.suggested_fix && <span> Correction proposée : {item.suggested_fix}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {(review.missing_keywords || []).length > 0 && (
            <p className="cv-ai-review-missing">
              <strong>Mots-clés ou preuves manquants :</strong> {review.missing_keywords.join(', ')}
            </p>
          )}
        </details>
      )}
    </section>
  )
}
