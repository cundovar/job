import { useState, useEffect } from 'react'
import './App.css'

const DATA_URL = '/data'

// Formate "YYYY-MM-DD" en "JJ/MM/AAAA"
function fmtDate(iso) {
  if (!iso) return ''
  const [y, m, d] = iso.split('-')
  return `${d}/${m}/${y}`
}

// Formate "YYYY-MM-DD" en "JJ/MM" (sans l'année)
function fmtShort(iso) {
  if (!iso) return ''
  const [, m, d] = iso.split('-')
  return `${d}/${m}`
}

function hasGeneratedCv(status) {
  return Boolean(
    status?.files?.['cv_final.md'] ||
    status?.files?.['cv_canva_copy.md'] ||
    status?.files?.['cv_final.html']
  )
}

function isProbablyHtml(response, text) {
  const contentType = response.headers.get('content-type') || ''
  return contentType.includes('text/html') || text.trimStart().startsWith('<!doctype html')
}

function cvFileUrl(id, file, status) {
  if (status?.source === 'static') return `${DATA_URL}/cv/${id}/${file}`
  return `/api/applications/${id}/cv/download/${file}`
}

function CandidaturesView() {
  const [candidatures, setCandidatures] = useState([])
  const [statuts, setStatuts] = useState({})       // { [id]: { status, applied_at, follow_up_at } }
  const [backendOk, setBackendOk] = useState(true)  // false si le backend est injoignable
  const [selected, setSelected] = useState(null)
  const [copied, setCopied] = useState(false)
  const [pendingId, setPendingId] = useState(null)  // id en cours de traitement (spinner)
  const [apiError, setApiError] = useState(null)    // message d'erreur discret
  const [cvStatuses, setCvStatuses] = useState({})  // { [id]: { exists, files, review } }
  const [cvPreviews, setCvPreviews] = useState({})   // { [id]: contenu cv_canva_copy.md }
  const [cvPendingId, setCvPendingId] = useState(null)
  const [cvError, setCvError] = useState(null)

  // Charge les candidatures depuis le fichier JSON statique
  useEffect(() => {
    fetch(`${DATA_URL}/candidatures.json`)
      .then(r => r.json())
      .then(d => setCandidatures(d.candidatures || []))
      .catch(() => {})
  }, [])

  // Charge les statuts depuis le backend (avec dégradation si indisponible)
  useEffect(() => {
    fetch('/api/applications')
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(list => {
        // Construit un dict { id → { status, applied_at, follow_up_at } }
        const map = {}
        list.forEach(item => { map[item.id] = item })
        setStatuts(map)
        setBackendOk(true)
      })
      .catch(() => {
        // Backend indisponible : on continue sans statuts (dégradation propre)
        setBackendOk(false)
      })
  }, [])

  const copyLettre = (text) => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const refreshCvStatus = async (id) => {
    if (!id) return null
    try {
      if (backendOk) {
        const res = await fetch(`/api/applications/${id}/cv/status`)
        const raw = await res.text()
        if (res.ok && !isProbablyHtml(res, raw)) {
          const status = JSON.parse(raw)
          setCvStatuses(prev => ({ ...prev, [id]: status }))
          return status
        }
      }

      // Fallback production : les CV générés hors conteneur sont publiés en statique.
      const staticRes = await fetch(`${DATA_URL}/cv/${id}/status.json`)
      if (!staticRes.ok) throw new Error(`HTTP ${staticRes.status}`)
      const status = await staticRes.json()
      const withSource = { ...status, source: 'static' }
      setCvStatuses(prev => ({ ...prev, [id]: withSource }))
      return withSource
    } catch {
      return null
    }
  }

  const refreshCvPreview = async (id) => {
    if (!id) return null
    try {
      if (backendOk) {
        const res = await fetch(`/api/applications/${id}/cv/download/cv_canva_copy.md`)
        const text = await res.text()
        if (res.ok && !isProbablyHtml(res, text)) {
          setCvPreviews(prev => ({ ...prev, [id]: text }))
          return text
        }
      }

      // Fallback production statique.
      const staticRes = await fetch(`${DATA_URL}/cv/${id}/cv_canva_copy.md`)
      if (!staticRes.ok) throw new Error(`HTTP ${staticRes.status}`)
      const text = await staticRes.text()
      setCvPreviews(prev => ({ ...prev, [id]: text }))
      return text
    } catch {
      return null
    }
  }

  const handlePrepareCv = async (id) => {
    setCvPendingId(id)
    setCvError(null)
    try {
      const res = await fetch(`/api/applications/${id}/cv/prepare`, { method: 'POST' })
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload.error || `HTTP ${res.status}`)
      setCvStatuses(prev => ({ ...prev, [id]: payload.status }))
      if (hasGeneratedCv(payload.status)) refreshCvPreview(id)
    } catch (err) {
      setCvError(err.message || 'Impossible de générer le CV personnalisé.')
    } finally {
      setCvPendingId(null)
    }
  }

  useEffect(() => {
    if (!selected) return
    refreshCvStatus(selected).then(status => {
      if (hasGeneratedCv(status)) refreshCvPreview(selected)
    })
  }, [selected, backendOk])

  // Marque une candidature comme postulée
  const handleApplied = async (e, id) => {
    e.stopPropagation()
    setPendingId(id)
    setApiError(null)
    try {
      const res = await fetch(`/api/applications/${id}/applied`, { method: 'POST' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const record = await res.json()
      setStatuts(prev => ({ ...prev, [id]: record }))
    } catch {
      setApiError('Impossible de contacter le serveur. Réessaie dans un instant.')
    } finally {
      setPendingId(null)
    }
  }

  // Annule le statut "postulé"
  const handleNotApplied = async (e, id) => {
    e.stopPropagation()
    setPendingId(id)
    setApiError(null)
    try {
      const res = await fetch(`/api/applications/${id}/not-applied`, { method: 'POST' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const record = await res.json()
      setStatuts(prev => ({ ...prev, [id]: record }))
    } catch {
      setApiError('Impossible de contacter le serveur. Réessaie dans un instant.')
    } finally {
      setPendingId(null)
    }
  }

  // Vue détail d'une candidature
  if (selected) {
    const c = candidatures.find(x => x.id === selected)
    const s = statuts[selected]
    const cvStatus = cvStatuses[selected]
    const cvReady = hasGeneratedCv(cvStatus)
    const cvReview = cvStatus?.review
    const cvPreview = cvPreviews[selected]
    return (
      <div className="candidature-detail">
        <button className="tab back-btn" onClick={() => setSelected(null)}>← Retour</button>
        <h1>📝 Lettre de motivation</h1>
        <div className="candidature-meta">
          <span><strong>{c?.entreprise}</strong></span>
          <span>📋 {c?.poste}</span>
          <span>📅 {c?.date}</span>
        </div>

        {/* Bouton / badge postulé dans la vue détail */}
        <div className="postule-zone">
          {!backendOk && (
            <span className="postule-offline">⚠️ Backend indisponible — statut non sauvegardé</span>
          )}
          {backendOk && s?.status === 'applied' ? (
            <div className="postule-applied">
              <span className="badge-applied">✅ Postulé le {fmtDate(s.applied_at)} · relance le {fmtShort(s.follow_up_at)}</span>
              <button
                className="annuler-btn"
                onClick={e => handleNotApplied(e, selected)}
                disabled={pendingId === selected}
              >
                {pendingId === selected ? '…' : 'annuler'}
              </button>
            </div>
          ) : backendOk ? (
            <button
              className="postule-btn"
              onClick={e => handleApplied(e, selected)}
              disabled={pendingId === selected}
            >
              {pendingId === selected ? 'En cours…' : '✅ J\'ai postulé'}
            </button>
          ) : null}
          {apiError && <span className="postule-error">{apiError}</span>}
        </div>

        <button className="copy-btn" onClick={() => copyLettre(c?.lettre || '')}>
          {copied ? '✅ Copié !' : '📋 Copier la lettre'}
        </button>
        <pre className="lettre-content">{c?.lettre}</pre>
        {c?.mail && (
          <>
            <h2>📧 Email de candidature</h2>
            <button className="copy-btn" onClick={() => copyLettre(c?.mail || '')}>
              {copied ? '✅ Copié !' : '📋 Copier l\'email'}
            </button>
            <pre className="lettre-content">{c?.mail}</pre>
          </>
        )}
        {c?.cv_recommande && (
          <>
            <h2>📄 CV Recommandé</h2>
            <pre className="lettre-content">{c?.cv_recommande}</pre>
          </>
        )}

        <section className="cv-generator-panel" aria-labelledby="cv-generator-title">
          <div className="cv-generator-heading">
            <h2 id="cv-generator-title">🎯 CV personnalisé</h2>
            <span className="optional-badge">Optionnel</span>
          </div>
          <p className="cv-generator-help">
            La lettre est déjà prête. Générez un CV adapté uniquement si vous souhaitez en joindre un à cette candidature.
          </p>
          <div className="cv-actions">
            <button
              type="button"
              className="prepare-btn"
              onClick={() => handlePrepareCv(selected)}
              disabled={!backendOk || cvPendingId === selected}
              aria-busy={cvPendingId === selected}
            >
              {cvPendingId === selected ? 'Génération du CV…' : cvReady ? '🔁 Régénérer le CV personnalisé' : '🎯 Générer le CV personnalisé'}
            </button>
            {cvReady && (
              <>
                <a className="download-btn" href={cvFileUrl(selected, 'cv_final.pdf', cvStatus)} download>📄 Télécharger PDF</a>
                <a className="download-btn" href={cvFileUrl(selected, 'cv_final.md', cvStatus)} download>⬇️ Télécharger MD</a>
                <a className="download-btn" href={cvFileUrl(selected, 'cv_canva_copy.md', cvStatus)} download>📋 Télécharger Canva</a>
                <a className="download-btn" href={cvFileUrl(selected, 'cv_final.html', cvStatus)} download>🌐 Télécharger HTML</a>
                <a className="download-btn" href={cvFileUrl(selected, 'cv_final.json', cvStatus)} download>JSON</a>
              </>
            )}
          </div>
          {!backendOk && <p className="cv-generator-note">Le backend doit être disponible pour générer le CV.</p>}
          {cvError && <p className="postule-error" role="alert">{cvError}</p>}
          {cvReview && (
            <div className="cv-review">
              <span>Qualité : <strong>{cvReview.quality_score}/100</strong></span>
              <span>ATS : <strong>{cvReview.ats_score}/100</strong></span>
              <span>Statut : <strong>{cvReview.status}</strong></span>
            </div>
          )}
          {cvReady && cvPreview && (
            <>
              <h3>👀 Aperçu CV — version Canva</h3>
              <button className="copy-btn" onClick={() => copyLettre(cvPreview)}>
                {copied ? '✅ Copié !' : '📋 Copier le CV Canva'}
              </button>
              <pre className="lettre-content">{cvPreview}</pre>
            </>
          )}
        </section>
      </div>
    )
  }

  // Vue liste des candidatures
  return (
    <div className="candidatures-list">
      <h1>📝 Candidatures préparées ({candidatures.length})</h1>

      {!backendOk && (
        <div className="backend-warning">
          ⚠️ Serveur backend indisponible — les statuts ne peuvent pas être enregistrés.
          Lance <code>cd server &amp;&amp; npm start</code> pour activer la persistance.
        </div>
      )}

      {apiError && (
        <div className="backend-warning">{apiError}</div>
      )}

      {candidatures.length === 0 && (
        <div className="empty-state"><p>Aucune candidature préparée. Demande "prépare candidature n°X".</p></div>
      )}

      {candidatures.map(c => {
        const s = statuts[c.id]
        const isApplied = s?.status === 'applied'
        const isPending = pendingId === c.id

        return (
          <article key={c.id} className={`job-card postuler ${isApplied ? 'is-applied' : ''}`} onClick={() => setSelected(c.id)} style={{cursor:'pointer'}}>
            <div className="job-header">
              <h3>{c.entreprise} — {c.poste}</h3>
              <div className="card-badges">
                {isApplied
                  ? <span className="badge-applied-small">✅ Postulé</span>
                  : <span className="badge-postuler">PRÊTE</span>
                }
              </div>
            </div>
            <div className="job-meta">
              <span>📅 {c.date}</span>
              {c.cv_recommande && <span>📄 {c.cv_recommande.split('\n')[0]?.substring(0, 50)}</span>}
              {isApplied && s.applied_at && (
                <span className="meta-applied">
                  Postulé le {fmtDate(s.applied_at)} · relance le {fmtShort(s.follow_up_at)}
                </span>
              )}
            </div>
            <p className="job-analysis" style={{fontStyle:'normal'}}>
              {c.lettre?.substring(0, 200)}...
            </p>

            {/* Zone bouton — stopPropagation pour ne pas ouvrir le détail */}
            <div className="postule-actions" onClick={e => e.stopPropagation()}>
              {backendOk && isApplied ? (
                <button
                  className="annuler-btn"
                  onClick={e => handleNotApplied(e, c.id)}
                  disabled={isPending}
                >
                  {isPending ? '…' : 'Annuler postulation'}
                </button>
              ) : backendOk ? (
                <button
                  className="postule-btn"
                  onClick={e => handleApplied(e, c.id)}
                  disabled={isPending}
                >
                  {isPending ? 'En cours…' : '✅ J\'ai postulé'}
                </button>
              ) : (
                <span className="postule-offline">Backend hors ligne</span>
              )}
            </div>
          </article>
        )
      })}
    </div>
  )
}

// Vue des candidatures déjà postulées (status === 'applied')
function PostuleesView() {
  const [postulees, setPostulees] = useState([])   // statut + détails fusionnés
  const [backendOk, setBackendOk] = useState(true)
  const [selected, setSelected] = useState(null)
  const [copied, setCopied] = useState(false)
  const [pendingId, setPendingId] = useState(null)
  const [apiError, setApiError] = useState(null)

  // Date du jour en format ISO YYYY-MM-DD pour comparer les dates de relance
  const today = new Date().toISOString().slice(0, 10)

  useEffect(() => {
    Promise.all([
      fetch(`${DATA_URL}/candidatures.json`).then(r => r.json()).catch(() => ({ candidatures: [] })),
      fetch('/api/applications').then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
    ])
      .then(([dataJson, appList]) => {
        const cands = dataJson.candidatures || []
        const applied = appList.filter(a => a.status === 'applied')
        // Croise les statuts avec les détails (lettre, entreprise, poste…)
        const enriched = applied.map(a => {
          const details = cands.find(c => c.id === a.id) || {}
          return { ...details, ...a }
        })
        // Tri par date de relance ascendante : les dépassées (overdue) remontent en haut
        enriched.sort((a, b) => {
          if (!a.follow_up_at) return 1
          if (!b.follow_up_at) return -1
          return a.follow_up_at.localeCompare(b.follow_up_at)
        })
        setPostulees(enriched)
        setBackendOk(true)
      })
      .catch(() => setBackendOk(false))
  }, [])

  const copyLettre = (text) => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Annule le statut "postulé" et retire la carte de la liste
  const handleNotApplied = async (e, id) => {
    e.stopPropagation()
    setPendingId(id)
    setApiError(null)
    try {
      const res = await fetch(`/api/applications/${id}/not-applied`, { method: 'POST' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setPostulees(prev => prev.filter(p => p.id !== id))
    } catch {
      setApiError('Impossible de contacter le serveur. Réessaie dans un instant.')
    } finally {
      setPendingId(null)
    }
  }

  // Vue détail lettre
  if (selected) {
    const c = postulees.find(p => p.id === selected)
    const isDue = c?.follow_up_at && c.follow_up_at <= today
    return (
      <div className="candidature-detail">
        <button className="tab back-btn" onClick={() => setSelected(null)}>← Retour</button>
        <h1>✅ Candidature postulée</h1>
        <div className="candidature-meta">
          <span><strong>{c?.entreprise}</strong></span>
          <span>📋 {c?.poste}</span>
          <span>📅 Postulé le {fmtDate(c?.applied_at)}</span>
          <span>
            🔔 Relance le {fmtDate(c?.follow_up_at)}
            {isDue && <span className="badge-relance-due"> ⏰ À relancer !</span>}
          </span>
        </div>
        <div className="postule-zone">
          <button
            className="annuler-btn"
            onClick={e => handleNotApplied(e, selected)}
            disabled={pendingId === selected}
          >
            {pendingId === selected ? '…' : 'Annuler la postulation'}
          </button>
          {apiError && <span className="postule-error">{apiError}</span>}
        </div>
        {c?.lettre && (
          <>
            <h2>📝 Lettre de motivation</h2>
            <button className="copy-btn" onClick={() => copyLettre(c.lettre)}>
              {copied ? '✅ Copié !' : '📋 Copier la lettre'}
            </button>
            <pre className="lettre-content">{c.lettre}</pre>
          </>
        )}
        {c?.mail && (
          <>
            <h2>📧 Email de candidature</h2>
            <button className="copy-btn" onClick={() => copyLettre(c.mail)}>
              {copied ? '✅ Copié !' : '📋 Copier l\'email'}
            </button>
            <pre className="lettre-content">{c.mail}</pre>
          </>
        )}
      </div>
    )
  }

  // Dégradation propre si backend injoignable
  if (!backendOk) {
    return (
      <div className="candidatures-list">
        <h1>✅ Candidatures postulées</h1>
        <div className="backend-warning">
          ⚠️ Serveur backend indisponible — impossible de charger les candidatures postulées.
          Lance <code>cd server &amp;&amp; npm start</code> pour activer la persistance.
        </div>
      </div>
    )
  }

  return (
    <div className="candidatures-list">
      <h1>✅ Candidatures postulées ({postulees.length})</h1>

      {apiError && <div className="backend-warning">{apiError}</div>}

      {postulees.length === 0 && (
        <div className="empty-state">
          <p>
            Aucune candidature postulée pour l'instant.<br />
            Va dans 📝 Candidatures et clique "✅ J'ai postulé".
          </p>
        </div>
      )}

      {postulees.map(p => {
        const isDue = p.follow_up_at && p.follow_up_at <= today
        const isPending = pendingId === p.id
        return (
          <article
            key={p.id}
            className="job-card is-applied"
            onClick={() => setSelected(p.id)}
            style={{ cursor: 'pointer' }}
          >
            <div className="job-header">
              <h3>{p.entreprise} — {p.poste}</h3>
              <div className="card-badges">
                {isDue
                  ? <span className="badge-relance-due">⏰ À relancer !</span>
                  : <span className="badge-applied-small">✅ Postulé</span>
                }
              </div>
            </div>
            <div className="job-meta">
              <span>📅 Postulé le {fmtDate(p.applied_at)}</span>
              <span>🔔 Relance le {fmtDate(p.follow_up_at)}</span>
            </div>
            <div className="postule-actions" onClick={e => e.stopPropagation()}>
              <button
                className="annuler-btn"
                onClick={e => handleNotApplied(e, p.id)}
                disabled={isPending}
              >
                {isPending ? '…' : 'Annuler la postulation'}
              </button>
            </div>
          </article>
        )
      })}
    </div>
  )
}

function AgenciesView() {
  const [payload, setPayload] = useState(null)
  const [fetchError, setFetchError] = useState(false)

  useEffect(() => {
    fetch(`${DATA_URL}/agencies/latest.json`)
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json() })
      .then(data => { setPayload(data); setFetchError(false) })
      .catch(() => { setPayload(null); setFetchError(true) })
  }, [])

  const agencies = payload?.agencies || []

  return (
    <div className="agencies-list">
      <header className="search-header">
        <h1>🏢 Agences web ({agencies.length})</h1>
        <div className="stats">
          <span>Prospection hors annonces</span>
          {payload?.generated_at && <span>Dernière maj : {payload.generated_at.replace('T', ' ')}</span>}
        </div>
      </header>

      {fetchError && (
        <div className="empty-state">
          <p>Données agences non disponibles. Lance “lance prospection agences web”.</p>
        </div>
      )}

      {!fetchError && agencies.length === 0 && (
        <div className="empty-state">
          <p>Aucune agence retenue pour l’instant. Relance une prospection agences web.</p>
        </div>
      )}

      <div className="job-list">
        {agencies.map((agency, i) => (
          <article key={agency.website || i} className="job-card agency-card">
            <div className="job-header">
              <h3>{i + 1}. {agency.name}</h3>
              <span className="badge-agency">{agency.score ?? '?'} / 100</span>
            </div>
            <div className="job-meta">
              {agency.stack?.length > 0 && <span>🧰 {agency.stack.join(', ')}</span>}
              {agency.emails?.length > 0 && <span>📧 {agency.emails[0]}</span>}
              <span>🔎 {agency.query}</span>
            </div>
            {agency.reasons?.length > 0 && (
              <div className="job-points">
                <strong>Pourquoi c’est intéressant :</strong>
                <ul>{agency.reasons.slice(0, 5).map((r, idx) => <li key={idx}>{r}</li>)}</ul>
              </div>
            )}
            <div className="agency-actions">
              {agency.website && (
                <a href={agency.website} target="_blank" rel="noopener noreferrer" className="job-link">
                  🌐 Ouvrir le site
                </a>
              )}
              {agency.contact_urls?.[0] && (
                <a href={agency.contact_urls[0]} target="_blank" rel="noopener noreferrer" className="job-link">
                  📬 Contact / recrutement
                </a>
              )}
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}

const WEATHER_CODES = {
  0: ['☀️', 'Ciel dégagé'],
  1: ['🌤️', 'Principalement dégagé'],
  2: ['⛅', 'Partiellement nuageux'],
  3: ['☁️', 'Couvert'],
  45: ['🌫️', 'Brouillard'],
  48: ['🌫️', 'Brouillard givrant'],
  51: ['🌦️', 'Bruine faible'],
  53: ['🌦️', 'Bruine modérée'],
  55: ['🌧️', 'Bruine dense'],
  61: ['🌧️', 'Pluie faible'],
  63: ['🌧️', 'Pluie modérée'],
  65: ['🌧️', 'Forte pluie'],
  71: ['🌨️', 'Neige faible'],
  73: ['🌨️', 'Neige modérée'],
  75: ['❄️', 'Forte neige'],
  80: ['🌦️', 'Averses faibles'],
  81: ['🌧️', 'Averses modérées'],
  82: ['⛈️', 'Fortes averses'],
  95: ['⛈️', 'Orage'],
  96: ['⛈️', 'Orage avec grêle'],
  99: ['⛈️', 'Orage violent avec grêle'],
}

function weatherLabel(code) {
  return WEATHER_CODES[code] || ['🌡️', 'Conditions inconnues']
}

function formatHour(date) {
  return new Intl.DateTimeFormat('fr-FR', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(date))
}

function formatDay(date) {
  return new Intl.DateTimeFormat('fr-FR', {
    weekday: 'short',
    day: '2-digit',
    month: '2-digit',
  }).format(new Date(date))
}

function WeatherView() {
  const [query, setQuery] = useState('Paris')
  const [place, setPlace] = useState(null)
  const [weather, setWeather] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const loadWeather = async (city = query) => {
    const trimmed = city.trim()
    if (!trimmed) return

    setLoading(true)
    setError(null)

    try {
      const geoRes = await fetch(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(trimmed)}&count=1&language=fr&format=json`)
      if (!geoRes.ok) throw new Error(`Géocodage HTTP ${geoRes.status}`)
      const geo = await geoRes.json()
      const found = geo.results?.[0]
      if (!found) throw new Error('Ville introuvable')

      const forecastUrl = new URL('https://api.open-meteo.com/v1/forecast')
      forecastUrl.searchParams.set('latitude', found.latitude)
      forecastUrl.searchParams.set('longitude', found.longitude)
      forecastUrl.searchParams.set('current', 'temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m')
      forecastUrl.searchParams.set('hourly', 'temperature_2m,weather_code,precipitation_probability')
      forecastUrl.searchParams.set('daily', 'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max')
      forecastUrl.searchParams.set('forecast_days', '5')
      forecastUrl.searchParams.set('timezone', 'auto')

      const weatherRes = await fetch(forecastUrl)
      if (!weatherRes.ok) throw new Error(`Météo HTTP ${weatherRes.status}`)
      const data = await weatherRes.json()

      setPlace(found)
      setWeather(data)
      setQuery(`${found.name}${found.admin1 ? `, ${found.admin1}` : ''}`)
    } catch (err) {
      setWeather(null)
      setPlace(null)
      setError(err.message || 'Impossible de charger la météo')
    } finally {
      setLoading(false)
    }
  }

  const loadDeviceLocation = () => {
    if (!navigator.geolocation) {
      setError('Géolocalisation non supportée par ce navigateur.')
      return
    }

    setLoading(true)
    setError(null)
    navigator.geolocation.getCurrentPosition(async position => {
      try {
        const { latitude, longitude } = position.coords
        const forecastUrl = new URL('https://api.open-meteo.com/v1/forecast')
        forecastUrl.searchParams.set('latitude', latitude)
        forecastUrl.searchParams.set('longitude', longitude)
        forecastUrl.searchParams.set('current', 'temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m')
        forecastUrl.searchParams.set('hourly', 'temperature_2m,weather_code,precipitation_probability')
        forecastUrl.searchParams.set('daily', 'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max')
        forecastUrl.searchParams.set('forecast_days', '5')
        forecastUrl.searchParams.set('timezone', 'auto')

        const weatherRes = await fetch(forecastUrl)
        if (!weatherRes.ok) throw new Error(`Météo HTTP ${weatherRes.status}`)
        const data = await weatherRes.json()

        setPlace({ name: 'Position actuelle', latitude, longitude })
        setWeather(data)
        setQuery('Position actuelle')
      } catch (err) {
        setWeather(null)
        setPlace(null)
        setError(err.message || 'Impossible de charger la météo')
      } finally {
        setLoading(false)
      }
    }, () => {
      setLoading(false)
      setError('Accès à la position refusé ou indisponible.')
    })
  }

  useEffect(() => {
    loadWeather('Paris')
  }, [])

  const current = weather?.current
  const [currentIcon, currentText] = weatherLabel(current?.weather_code)
  const nextHours = weather?.hourly?.time
    ?.map((time, index) => ({
      time,
      temp: weather.hourly.temperature_2m[index],
      code: weather.hourly.weather_code[index],
      rain: weather.hourly.precipitation_probability[index],
    }))
    .filter(item => new Date(item.time) >= new Date())
    .slice(0, 8) || []

  return (
    <div className="weather-view">
      <header className="search-header">
        <h1>🌦️ Météo en direct</h1>
        <div className="stats">
          <span>Sans backend</span>
          <span>Source : Open-Meteo</span>
        </div>
      </header>

      <form className="weather-search" onSubmit={e => { e.preventDefault(); loadWeather() }}>
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Ville, ex. Paris"
          aria-label="Ville"
        />
        <button type="submit" className="prepare-btn" disabled={loading}>
          {loading ? 'Chargement…' : 'Rechercher'}
        </button>
        <button type="button" className="copy-btn weather-location-btn" onClick={loadDeviceLocation} disabled={loading}>
          📍 Ma position
        </button>
      </form>

      {error && <div className="backend-warning">{error}</div>}

      {current && (
        <>
          <section className="weather-current">
            <div>
              <p className="weather-place">
                {place?.name}
                {place?.country && <span>, {place.country}</span>}
              </p>
              <p className="weather-updated">Mis à jour : {formatHour(current.time)}</p>
            </div>
            <div className="weather-main">
              <span className="weather-icon">{currentIcon}</span>
              <div>
                <div className="weather-temp">{Math.round(current.temperature_2m)}°C</div>
                <div className="weather-desc">{currentText}</div>
              </div>
            </div>
            <div className="weather-metrics">
              <span>Ressenti {Math.round(current.apparent_temperature)}°C</span>
              <span>Humidité {current.relative_humidity_2m}%</span>
              <span>Vent {Math.round(current.wind_speed_10m)} km/h</span>
            </div>
          </section>

          <section className="weather-section">
            <h2>Prochaines heures</h2>
            <div className="weather-hourly">
              {nextHours.map(hour => {
                const [icon, text] = weatherLabel(hour.code)
                return (
                  <article key={hour.time} className="weather-mini-card">
                    <span>{formatHour(hour.time)}</span>
                    <strong>{icon} {Math.round(hour.temp)}°C</strong>
                    <small>{text}</small>
                    <small>Pluie {hour.rain ?? 0}%</small>
                  </article>
                )
              })}
            </div>
          </section>

          <section className="weather-section">
            <h2>5 jours</h2>
            <div className="weather-daily">
              {weather.daily.time.map((day, index) => {
                const [icon, text] = weatherLabel(weather.daily.weather_code[index])
                return (
                  <article key={day} className="weather-day-card">
                    <span>{formatDay(day)}</span>
                    <strong>{icon} {text}</strong>
                    <span>{Math.round(weather.daily.temperature_2m_min[index])}° / {Math.round(weather.daily.temperature_2m_max[index])}°</span>
                    <span>Pluie {weather.daily.precipitation_probability_max[index] ?? 0}%</span>
                  </article>
                )
              })}
            </div>
          </section>
        </>
      )}
    </div>
  )
}

// Poll /api/search/status toutes les 5s tant qu'une recherche tourne
function useSearchRunner() {
  const [status, setStatus] = useState({ running: false, lastResult: null, error: null })
  const [launching, setLaunching] = useState(false)

  useEffect(() => {
    let timer = null
    let cancelled = false

    const poll = async () => {
      try {
        const res = await fetch('/api/search/status')
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        if (cancelled) return
        setStatus(data)
        if (data.running) {
          timer = setTimeout(poll, 5000)
        }
      } catch {
        if (!cancelled) timer = setTimeout(poll, 8000)
      }
    }
    poll()

    return () => { cancelled = true; if (timer) clearTimeout(timer) }
  }, [])

  const launch = async () => {
    setLaunching(true)
    try {
      const res = await fetch('/api/search/run', { method: 'POST' })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)
      setStatus(data)
      // Relance immédiatement le polling (le useEffect ci-dessus gère le suivi tant que running=true)
      if (data.running) {
        const poll = async () => {
          try {
            const r = await fetch('/api/search/status')
            const d = await r.json()
            setStatus(d)
            if (d.running) setTimeout(poll, 5000)
          } catch {
            setTimeout(poll, 8000)
          }
        }
        setTimeout(poll, 5000)
      }
    } catch (err) {
      setStatus(prev => ({ ...prev, error: err.message || 'Erreur au lancement' }))
    } finally {
      setLaunching(false)
    }
  }

  return { status, launching, launch }
}

function App() {
  const [index, setIndex] = useState(null)
  const [activeSearch, setActiveSearch] = useState(null)
  const [activeCategory, setActiveCategory] = useState('backend')
  const [activeMode, setActiveMode] = useState('recherche')  // 'recherche' | 'agencies' | 'candidatures' | 'postulees' | 'weather'
  const [nbPostulees, setNbPostulees] = useState(0)          // compteur sidebar dynamique
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(false)
  const [fetchError, setFetchError] = useState(false)
  const [preparePendingKey, setPreparePendingKey] = useState(null)
  const [prepareMessage, setPrepareMessage] = useState(null)
  const { status: searchStatus, launching: searchLaunching, launch: launchSearch } = useSearchRunner()

  useEffect(() => {
    fetch(`${DATA_URL}/index.json`)
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json() })
      .then(data => {
        setIndex(data)
        if (data.searches?.length > 0) {
          setActiveSearch(data.searches[0].id)
        }
      })
      .catch(() => console.log('Index not found yet'))
  }, [])

  useEffect(() => {
    if (!activeSearch || !index) return
    const search = index.searches.find(s => s.id === activeSearch)
    if (!search) return
    const cats = Object.keys(search.categories)
    if (cats.length > 0 && !cats.includes(activeCategory)) {
      queueMicrotask(() => setActiveCategory(cats[0]))
    }
  }, [activeSearch, activeCategory, index])

  // Charge le nombre de candidatures postulées pour l'afficher dans la sidebar
  useEffect(() => {
    fetch('/api/applications')
      .then(r => r.ok ? r.json() : [])
      .then(list => setNbPostulees(list.filter(a => a.status === 'applied').length))
      .catch(() => {})
  }, [activeMode])  // se rafraîchit quand on change de mode

  useEffect(() => {
    if (!activeSearch || activeMode !== 'recherche') return
    queueMicrotask(() => {
      setLoading(true)
      setFetchError(false)
    })
    fetch(`${DATA_URL}/${activeSearch}/${activeCategory}.json`)
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json() })
      .then(data => setJobs(data.jobs || []))
      .catch(() => { setJobs([]); setFetchError(true) })
      .finally(() => setLoading(false))
  }, [activeSearch, activeCategory, activeMode])

  const handlePrepareCandidature = async (job) => {
    const key = job.url || `${job.title}-${job.company}`
    setPreparePendingKey(key)
    setPrepareMessage(null)
    try {
      const res = await fetch('/api/applications/prepare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)
      setPrepareMessage({ type: 'success', text: `Lettre de motivation prête : ${data.id}` })
      setActiveMode('candidatures')
    } catch (err) {
      setPrepareMessage({
        type: 'error',
        text: `Préparation impossible : ${err.message || 'serveur backend indisponible'}`,
      })
    } finally {
      setPreparePendingKey(null)
    }
  }

  const currentSearch = index?.searches?.find(s => s.id === activeSearch)

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <button
          className="prepare-btn launch-search-btn"
          onClick={launchSearch}
          disabled={searchLaunching || searchStatus.running}
          style={{ width: '100%', marginBottom: '.75rem' }}
        >
          {searchStatus.running ? '⏳ Recherche en cours…' : searchLaunching ? 'Lancement…' : '🚀 Lancer une recherche'}
        </button>
        {!searchStatus.running && searchStatus.lastResult && (
          <div className="search-stats" style={{ marginBottom: '1rem', lineHeight: 1.5 }}>
            Dernier run : {searchStatus.lastResult.total} offres
            {' · '}<span className="stats postuler">⭐ {searchStatus.lastResult.postuler}</span>
            {' · '}<span className="stats peut-etre">🟡 {searchStatus.lastResult.peut_etre}</span>
          </div>
        )}
        {searchStatus.error && (
          <div className="backend-warning" style={{ marginBottom: '1rem', fontSize: '.75rem' }}>{searchStatus.error}</div>
        )}
        <h2>🔍 Recherches</h2>
        <button
          className={`search-btn mode-btn ${activeMode === 'recherche' ? 'active' : ''}`}
          onClick={() => setActiveMode('recherche')}
        >
          <span className="search-date">🔍 Recherches</span>
          <span className="search-stats">{index?.searches?.length || 0} sessions</span>
        </button>
        <button
          className={`search-btn mode-btn ${activeMode === 'agencies' ? 'active' : ''}`}
          onClick={() => setActiveMode('agencies')}
        >
          <span className="search-date">🏢 Agences web</span>
          <span className="search-stats">Prospection hors annonces</span>
        </button>
        <button
          className={`search-btn mode-btn ${activeMode === 'candidatures' ? 'active' : ''}`}
          onClick={() => setActiveMode('candidatures')}
        >
          <span className="search-date">📝 Candidatures</span>
          <span className="search-stats">Lettres prêtes</span>
        </button>
        <button
          className={`search-btn mode-btn ${activeMode === 'postulees' ? 'active' : ''}`}
          onClick={() => setActiveMode('postulees')}
        >
          <span className="search-date">✅ Postulées</span>
          <span className="search-stats">{nbPostulees > 0 ? `${nbPostulees} postulées` : 'Aucune'}</span>
        </button>
        <button
          className={`search-btn mode-btn ${activeMode === 'weather' ? 'active' : ''}`}
          onClick={() => setActiveMode('weather')}
        >
          <span className="search-date">🌦️ Météo</span>
          <span className="search-stats">Direct sans backend</span>
        </button>
        <hr style={{borderColor:'#2a2a4a', margin:'1rem 0'}} />
        {index?.searches?.map(search => (
          <button
            key={search.id}
            className={`search-btn ${search.id === activeSearch && activeMode === 'recherche' ? 'active' : ''}`}
            onClick={() => { setActiveMode('recherche'); setActiveSearch(search.id) }}
          >
            <span className="search-date">{search.date}</span>
            <span className="search-stats">{search.total} offres · ⭐{search.postuler}</span>
          </button>
        ))}
      </aside>

      <main className="main-content">
        {activeMode === 'candidatures' ? (
          <CandidaturesView />
        ) : activeMode === 'postulees' ? (
          <PostuleesView />
        ) : activeMode === 'weather' ? (
          <WeatherView />
        ) : activeMode === 'agencies' ? (
          <AgenciesView />
        ) : currentSearch ? (
          <>
            <header className="search-header">
              <h1>Recherche du {currentSearch.date}</h1>
              <div className="stats">
                <span>{currentSearch.total} offres</span>
                <span className="postuler">⭐ {currentSearch.postuler} POSTULER</span>
                <span className="peut-etre">🟡 {currentSearch.peut_etre} PEUT-ÊTRE</span>
              </div>
              {prepareMessage && (
                <div className={`prepare-message ${prepareMessage.type}`}>
                  {prepareMessage.text}
                </div>
              )}
            </header>

            <nav className="tabs">
              {Object.entries(currentSearch.categories).map(([cat, info]) => (
                <button
                  key={cat}
                  className={`tab ${cat === activeCategory ? 'active' : ''}`}
                  onClick={() => setActiveCategory(cat)}
                >
                  {cat === 'backend' ? '💻 Backend' :
                   cat === 'frontend' ? '🎨 Frontend' :
                   cat === 'webmaster_formateur' ? '🌐🎓 Web & Formateur' :
                   '🚪 Nouvelles Portes'}
                  <span className="badge">{info.count}</span>
                </button>
              ))}
            </nav>

            {loading ? (
              <div className="loading">Chargement...</div>
            ) : fetchError ? (
              <div className="empty-state"><p>Données non disponibles.</p></div>
            ) : (
              <div className="job-list">
                {jobs.map((job, i) => {
                  const ai = job.ai_analysis || {}
                  const reco = ai.recommandation || '?'
                  const recoClass = reco === 'POSTULER' ? 'postuler' :
                                    reco === 'PASSER' ? 'passer' : 'peut-etre'
                  const prepareKey = job.url || `${job.title}-${job.company}`
                  const isPreparing = preparePendingKey === prepareKey
                  return (
                    <article key={i} className={`job-card ${recoClass}`}>
                      <div className="job-header">
                        <h3>{i + 1}. {job.title}</h3>
                        <span className={`badge-${recoClass}`}>{reco}</span>
                      </div>
                      <div className="job-meta">
                        <span>{job.company}</span>
                        <span>📍 {job.location}</span>
                        <span>📋 {job.contract_type || '?'}</span>
                        <span>📊 {job.score}/100</span>
                        {job.published_at && <span>📅 {job.published_at.slice(0, 10)}</span>}
                      </div>
                      {ai.raison_breve && <p className="job-analysis">💬 {ai.raison_breve}</p>}
                      {ai.points_forts?.length > 0 && (
                        <div className="job-points">
                          <strong>✅ Points forts :</strong>
                          <ul>{ai.points_forts.slice(0, 3).map((p, idx) => <li key={idx}>{p}</li>)}</ul>
                        </div>
                      )}
                      {ai.points_faibles?.length > 0 && (
                        <div className="job-points warning">
                          <strong>⚠️ Vigilance :</strong>
                          <ul>{ai.points_faibles.slice(0, 2).map((p, idx) => <li key={idx}>{p}</li>)}</ul>
                        </div>
                      )}
                      {job.url && (
                        <a href={job.url} target="_blank" rel="noopener noreferrer" className="job-link">
                          🔗 Voir l'offre
                        </a>
                      )}
                      <div className="prepare-actions">
                        <button
                          className="prepare-btn"
                          onClick={() => handlePrepareCandidature(job)}
                          disabled={isPreparing}
                        >
                          {isPreparing ? 'Création de la lettre…' : '📝 Créer la lettre de motivation'}
                        </button>
                      </div>
                    </article>
                  )
                })}
              </div>
            )}
          </>
        ) : (
          <div className="empty-state">
            <h2>Aucune recherche</h2>
            <p>Lance une recherche d'emploi pour voir les résultats ici.</p>
          </div>
        )}
      </main>
    </div>
  )
}

export default App
