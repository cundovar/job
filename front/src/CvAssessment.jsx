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

export default function CvAssessment({ assessment, legacyReview }) {
  if (!assessment) return <LegacyAssessment review={legacyReview} />
  const controls = ['eligibility', 'parseability', 'truthfulness']
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
        <span className={`cv-assessment-status ${assessment.overall_status || 'review'}`}>
          {STATUS_LABELS[assessment.overall_status] || 'À vérifier'}
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
    </section>
  )
}
