import { useState, useEffect, useRef, useCallback } from 'react'
import {
  AlarmClock, ArrowLeft, Bell, Briefcase, Building2, Calendar, Check, CircleCheck, CircleDot,
  Clipboard, Cloud, CloudDrizzle, CloudFog, CloudLightning, CloudRain, CloudSnow,
  CloudSun, DoorOpen, Ellipsis, ExternalLink, FileDown, FileText, Globe,
  GraduationCap, LoaderCircle, MapPin, Mail, MessageCircle, Palette, PenLine,
  Rocket, RotateCw, ShieldCheck,
  Search, Send, Server, Snowflake, Sparkles, Star, Sun, Target, Thermometer,
  TriangleAlert, Wrench,
} from 'lucide-react'
import './App.css'
import ManualCvView from './ManualCvView'
import AgencyScout from './AgencyScout'
import CvAssessment from './CvAssessment'
import HermesChat from './HermesChat'

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

function fmtTime(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
}

function fmtSession(search) {
  if (!search) return ''
  const label = fmtDate(search.date || search.id)
  const time = fmtTime(search.generated_at)
  return time ? `${label} · ${time}` : label
}

// Le statut de publication est calculé une seule fois, côté serveur. Le front
// ne redéduit plus « prêt » depuis la présence d'un fichier : c'était l'origine
// des trois définitions divergentes d'un CV prêt.
const CV_STATUS_LABELS = {
  preparing: 'Génération en cours',
  ready: 'CV prêt',
  review: 'À corriger',
  blocked: 'Bloqué',
  absent: 'Pas encore généré',
}

function cvPublicationStatus(status) {
  if (!status) return 'absent'
  if (['queued', 'running'].includes(status.generation?.state)) return 'preparing'
  return status.status || 'absent'
}

function hasGeneratedCv(status) {
  return cvPublicationStatus(status) === 'ready'
}

function cvExists(status) {
  return cvPublicationStatus(status) !== 'absent'
}

function isProbablyHtml(response, text) {
  const contentType = response.headers.get('content-type') || ''
  return contentType.includes('text/html') || text.trimStart().startsWith('<!doctype html')
}

function cvFileUrl(id, file, status) {
  if (status?.source === 'static') return `${DATA_URL}/cv/${id}/${file}`
  return `/api/applications/${id}/cv/download/${file}`
}

function CvDownloads({ cv }) {
  const status = { files: cv.files }
  // Hors `ready`, l'API refuse les fichiers finaux : on ne propose pas un lien
  // qui renverra une erreur, et on oriente vers l'aperçu à corriger.
  if (cv.status !== 'ready') {
    return (
      <div className="cv-library-downloads" aria-label={`Fichiers du CV ${cv.poste || cv.id}`}>
        {cv.reason && <p className="cv-library-reason">{cv.reason}</p>}
        {cv.files?.['cv_review_preview.pdf'] && (
          <a className="download-btn secondary" href={cvFileUrl(cv.id, 'cv_review_preview.pdf', status)} download>
            <FileDown /> Aperçu à corriger
          </a>
        )}
      </div>
    )
  }
  return (
    <div className="cv-library-downloads" aria-label={`Fichiers du CV ${cv.poste || cv.id}`}>
      {cv.files?.['cv_final.pdf'] && <a className="download-btn primary" href={cvFileUrl(cv.id, 'cv_final.pdf', status)} download><FileDown /> PDF design</a>}
      {cv.files?.['cv_ats.pdf'] && <a className="download-btn" href={cvFileUrl(cv.id, 'cv_ats.pdf', status)} download><FileDown /> PDF ATS</a>}
      {cv.files?.['cv_final.html'] && <a className="download-btn" href={cvFileUrl(cv.id, 'cv_final.html', status)} download><Globe /> HTML</a>}
      {cv.files?.['cv_final.json'] && <a className="download-btn" href={cvFileUrl(cv.id, 'cv_final.json', status)} download>JSON</a>}
    </div>
  )
}

function MesCvView() {
  const [cvs, setCvs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    fetch('/api/applications/cvs', { cache: 'no-store' })
      .then(async response => {
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`)
        return payload
      })
      .then(items => { if (active) setCvs(Array.isArray(items) ? items : []) })
      .catch(() => { if (active) setError('Impossible de charger les CV générés. Vérifie que le serveur est disponible.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  return (
    <section className="candidatures-list cv-library">
      <header className="cv-library-header">
        <div>
          <h1><FileText /> Mes CV</h1>
          <p>Les CV générés pour tes candidatures, prêts à télécharger.</p>
        </div>
        {!loading && <span className="badge">{cvs.length}</span>}
      </header>
      {loading && <div className="loading">Chargement des CV…</div>}
      {error && <div className="backend-warning"><TriangleAlert /> {error}</div>}
      {!loading && !error && cvs.length === 0 && (
        <div className="empty-state"><p>Aucun CV généré pour le moment. Génère un CV depuis une candidature préparée.</p></div>
      )}
      <div className="cv-library-list">
        {cvs.map(cv => (
          <article className="cv-library-card" key={cv.id}>
            <div>
              <div className="card-top">
                <span className={cv.status === 'ready' ? 'badge-postuler' : 'badge-peut-etre'}>
                  {CV_STATUS_LABELS[cv.status] || 'Incomplet'}
                </span>
              </div>
              <h2>{cv.poste || 'Poste non renseigné'}</h2>
              <p className="job-company">{cv.entreprise || 'Entreprise non renseignée'}</p>
              <p className="job-meta"><span><Calendar /> {fmtDate(cv.date)}</span></p>
            </div>
            <CvDownloads cv={cv} />
          </article>
        ))}
      </div>
    </section>
  )
}

const wait = ms => new Promise(resolve => setTimeout(resolve, ms))

// Suivi de la file de préparation côté backend (réponse 202 + polling) : une
// requête ouverte pendant les 20-40 s du script Python ne survivait pas au mobile.
async function waitForPreparation(taskId, initialStatus) {
  let status = initialStatus
  const deadline = Date.now() + 10 * 60 * 1000
  let networkErrors = 0

  while (Date.now() < deadline) {
    if (status?.state === 'completed') {
      if (!status.result?.id) throw new Error("L'identifiant de la candidature est absent.")
      return status.result
    }
    if (status?.state === 'failed') {
      throw new Error(status.error || 'La préparation de la candidature a échoué.')
    }

    await wait(2500)

    try {
      const res = await fetch(
        `/api/applications/prepare/status/${encodeURIComponent(taskId)}`,
        { cache: 'no-store' }
      )
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload.error || `HTTP ${res.status}`)
      status = payload
      networkErrors = 0
    } catch (err) {
      if (!(err instanceof TypeError)) throw err
      networkErrors += 1
      if (networkErrors >= 5) {
        throw new Error(
          'Le serveur est momentanément injoignable pendant la préparation.',
          { cause: err }
        )
      }
    }
  }

  throw new Error('La préparation dépasse 10 minutes. Réessayez plus tard.')
}

async function waitForAgencyTarget(taskId, initialStatus, onProgress) {
  let status = initialStatus
  const deadline = Date.now() + 30 * 60 * 1000
  let networkErrors = 0

  while (Date.now() < deadline) {
    onProgress?.(status)
    if (status?.state === 'completed') {
      if (!status.result?.ok) throw new Error('La préparation agence est incomplète.')
      return status.result
    }
    if (status?.state === 'failed') {
      throw new Error(status.error || 'La préparation de l’agence a échoué.')
    }

    await wait(2500)

    try {
      const res = await fetch(
        `/api/agencies/target/status/${encodeURIComponent(taskId)}`,
        { cache: 'no-store' }
      )
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload.error || `HTTP ${res.status}`)
      status = payload
      networkErrors = 0
    } catch (err) {
      const isNetworkError = err instanceof TypeError ||
        /failed to fetch|networkerror|injoignable/i.test(err.message || '')
      if (!isNetworkError) throw err
      networkErrors += 1
      if (networkErrors >= 5) {
        throw new Error(
          'Le serveur est momentanément injoignable pendant la préparation.',
          { cause: err }
        )
      }
    }
  }

  throw new Error('La préparation dépasse 30 minutes. Son état reste consultable plus tard.')
}

// Ce qui justifie l'envoi, à côté du brouillon. Sans ces preuves sous les yeux,
// approuver serait un acte de foi. Tout vient de job.json : rien n'est deviné,
// et les extraits de pages sont du texte inerte, jamais une consigne.
function PreuvesPanel({ preuves }) {
  if (!preuves) return null
  const constats = preuves.constats || []
  const contacts = preuves.contact || []

  return (
    <section className="preuves-panel" aria-labelledby="preuves-title">
      <h2 id="preuves-title"><ShieldCheck /> Ce qui est établi</h2>

      <dl className="preuves-identite">
        {preuves.url && (
          <>
            <dt>Site mesuré</dt>
            <dd>
              <a href={preuves.url} target="_blank" rel="noreferrer noopener">
                {preuves.url} <ExternalLink />
              </a>
            </dd>
          </>
        )}
        <dt>Adresse de destination</dt>
        <dd>
          {preuves.adresse
            ? <><strong>{preuves.adresse}</strong><span className="preuve-source">{preuves.adresse_source}</span></>
            : <span className="preuve-absente"><TriangleAlert /> Aucune adresse relevée en clair — ce dossier ne peut pas partir par email.</span>}
        </dd>
      </dl>

      {contacts.length > 0 && (
        <>
          <h3>Comment l'adresse a été trouvée</h3>
          <ul className="preuves-liste">
            {contacts.map((item, index) => (
              <li key={`contact-${index}`}>
                <p className="preuve-claim">{item.claim}</p>
                {item.evidence.map((evidence, i) => (
                  <pre key={i} className="preuve-evidence">{evidence}</pre>
                ))}
              </li>
            ))}
          </ul>
        </>
      )}

      <h3>Constats retenus ({constats.length})</h3>
      {constats.length === 0 ? (
        <p className="preuve-absente">Aucun constat. Rien ne devrait avoir été rédigé.</p>
      ) : (
        <ul className="preuves-liste">
          {constats.map((item, index) => (
            <li key={`constat-${index}`}>
              <p className="preuve-claim">
                <span className={`preuve-statut statut-${item.status.toLowerCase()}`}>{item.status}</span>
                {item.claim}
              </p>
              {item.evidence.map((evidence, i) => (
                <pre key={i} className="preuve-evidence">{evidence}</pre>
              ))}
              {item.source_tool && <p className="preuve-outil">mesuré par {item.source_tool}</p>}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

// `mission` sépare deux gestes qui ne se valident pas pareil : une candidature
// sur annonce se copie-colle sur un formulaire, une spontanée s'approuve avant
// de partir par email. Les mélanger dans une même liste rendait le bouton
// « Approuver » incompréhensible.
function CandidaturesView({ mission = 'annonce' }) {
  const spontanee = mission === 'spontanee'
  const [candidatures, setCandidatures] = useState([])
  const [statuts, setStatuts] = useState({})       // { [id]: { status, applied_at, follow_up_at } }
  const [backendOk, setBackendOk] = useState(true)  // false si le backend est injoignable
  const [selected, setSelected] = useState(null)
  const [copied, setCopied] = useState(false)
  const [pendingId, setPendingId] = useState(null)  // id en cours de traitement (spinner)
  const [apiError, setApiError] = useState(null)    // message d'erreur discret
  const [cvStatuses, setCvStatuses] = useState({})  // { [id]: { exists, files, review } }
  const [cvPendingId, setCvPendingId] = useState(null)
  const [cvFeedback, setCvFeedback] = useState(null) // { id, type, text }
  const [approvals, setApprovals] = useState({})    // { [id]: { status, approved } }
  const [approvalPendingId, setApprovalPendingId] = useState(null)
  const [sendBrevo, setSendBrevo] = useState({})    // { [id]: { pending, ok, to, cc, error } }
  const [recipientDrafts, setRecipientDrafts] = useState({}) // { [id]: { items, value, pending, error } }
  const [lettreRegen, setLettreRegen] = useState({})    // { [id]: { pending, ok, error } }
  const [editLettre, setEditLettre] = useState({})      // { [id]: { editing, value, pending, saved, error } }
  const [editMail, setEditMail] = useState({})          // { [id]: { editing, value, pending, saved, error } }
  const [cvReco, setCvReco] = useState({})              // { [id]: recommandations agent (préremplies) }
  const cvPollControllerRef = useRef(null)

  // Charge les candidatures depuis le fichier JSON statique. Le bloc `preuves`
  // n'existe que pour les dossiers de prospection : il suffit à les distinguer.
  useEffect(() => {
    fetch(`${DATA_URL}/candidatures.json`)
      .then(r => r.json())
      .then(d => setCandidatures((d.candidatures || []).filter(c => Boolean(c.preuves) === spontanee)))
      .catch(() => {})
  }, [spontanee])

  useEffect(() => {
    return () => {
      cvPollControllerRef.current?.abort()
      cvPollControllerRef.current = null
    }
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
        const res = await fetch(`/api/applications/${id}/cv/status`, { cache: 'no-store' })
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

  const waitForCvGeneration = async (id, signal) => {
    const deadline = Date.now() + 30 * 60 * 1000
    let consecutiveFetchErrors = 0

    while (Date.now() < deadline) {
      if (signal.aborted) throw new DOMException('Polling annulé', 'AbortError')
      await wait(2500)
      if (signal.aborted) throw new DOMException('Polling annulé', 'AbortError')
      try {
        const res = await fetch(`/api/applications/${id}/cv/status`, {
          cache: 'no-store',
          signal,
        })
        const payload = await res.json().catch(() => ({}))
        if (!res.ok) throw new Error(payload.error || `HTTP ${res.status}`)
        consecutiveFetchErrors = 0
        setCvStatuses(prev => ({ ...prev, [id]: payload }))

        if (payload.generation?.state === 'completed') {
          // Une génération peut aboutir à un CV « à corriger » : c'est un
          // résultat légitime, pas un échec technique.
          if (!cvExists(payload)) {
            throw new Error("La génération est terminée mais aucun CV n'a été produit.")
          }
          return payload
        }
        if (payload.generation?.state === 'failed') {
          throw new Error(payload.generation.error || 'La génération du CV a échoué.')
        }
        if (!payload.generation) {
          throw new Error('Le suivi de la génération a été interrompu. Relance la génération.')
        }
      } catch (err) {
        if (err.name === 'AbortError') throw err
        const isNetworkError = err instanceof TypeError || /failed to fetch|networkerror/i.test(err.message || '')
        if (!isNetworkError) {
          throw err
        }
        consecutiveFetchErrors += 1
        if (consecutiveFetchErrors >= 5) {
          throw new Error('Le serveur est momentanément injoignable pendant la génération.', { cause: err })
        }
      }
    }

    throw new Error('La génération prend plus de 30 minutes. Vérifie son état dans quelques instants.')
  }

  // Réarme le suivi de génération au (re)montage de la vue : quitter la page
  // avorte le polling précédent, mais la génération continue côté serveur —
  // au retour, un statut `queued/running` doit réafficher la progression et
  // ramener le feedback de fin, au lieu de laisser la carte muette.
  const ensureCvPolling = (id, status) => {
    if (!id || !status) return
    const state = status?.generation?.state
    if (!['queued', 'running'].includes(state)) return
    const existing = cvPollControllerRef.current
    if (existing && !existing.signal.aborted) return
    cvPollControllerRef.current?.abort()
    const controller = new AbortController()
    cvPollControllerRef.current = controller
    setCvPendingId(id)
    ;(async () => {
      try {
        const finalStatus = await waitForCvGeneration(id, controller.signal)
        setCvStatuses(prev => ({ ...prev, [id]: finalStatus }))
        if (!cvExists(finalStatus)) {
          setCvFeedback({
            id,
            type: 'error',
            text: 'Les fichiers attendus du CV sont absents.',
          })
        } else {
          setCvFeedback({
            id,
            type: 'success',
            text: 'CV personnalisé terminé. Le PDF est disponible au téléchargement.',
          })
        }
      } catch (err) {
        if (err.name === 'AbortError') return
        setCvFeedback({
          id,
          type: 'error',
          text: err.message || 'Suivi de la génération interrompu.',
        })
      } finally {
        setCvPendingId(null)
        if (cvPollControllerRef.current === controller) {
          cvPollControllerRef.current = null
        }
      }
    })()
  }

  const handlePrepareCv = async (id) => {
    setCvPendingId(id)
    setCvFeedback(null)
    cvPollControllerRef.current?.abort()
    const controller = new AbortController()
    cvPollControllerRef.current = controller
    try {
      const res = await fetch(`/api/applications/${id}/cv/prepare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ recommandations: cvReco[id] ?? '' }),
        signal: controller.signal,
      })
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload.error || `HTTP ${res.status}`)
      setCvStatuses(prev => ({ ...prev, [id]: payload.status }))

      const shouldPoll = ['queued', 'running'].includes(payload.status?.generation?.state)
      const finalStatus = shouldPoll
        ? await waitForCvGeneration(id, controller.signal)
        : payload.status
      setCvStatuses(prev => ({ ...prev, [id]: finalStatus }))
      if (!cvExists(finalStatus)) {
        throw new Error('Les fichiers attendus du CV sont absents.')
      }
      setCvFeedback({
        id,
        type: 'success',
        text: 'CV personnalisé terminé. Le PDF est disponible au téléchargement.',
      })
    } catch (err) {
      if (err.name === 'AbortError') return
      setCvFeedback({
        id,
        type: 'error',
        text: err.message || 'Impossible de générer le CV personnalisé.',
      })
    } finally {
      setCvPendingId(null)
      if (cvPollControllerRef.current === controller) {
        cvPollControllerRef.current = null
      }
    }
  }

  useEffect(() => {
    if (!selected) return
    const timeout = setTimeout(async () => {
      const status = await refreshCvStatus(selected)
      ensureCvPolling(selected, status)
    }, 0)
    return () => clearTimeout(timeout)
    // refreshCvStatus dépend déjà de backendOk, volontairement listé ci-dessous.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, backendOk])

  // Filet de resynchronisation : tant que le dossier affiché est « preparing »,
  // on relit le statut toutes les 5 s et on réarme le polling s'il est mort
  // (erreur réseau passagère, retour de page). Sans ce filet, un suivi rompu
  // laissait le bouton « Génération du CV… » figé après la fin réelle.
  const cvPreparing = cvPublicationStatus(cvStatuses[selected]) === 'preparing'
  useEffect(() => {
    if (!selected || !backendOk || !cvPreparing) return
    const timer = setInterval(async () => {
      const fresh = await refreshCvStatus(selected)
      if (fresh) ensureCvPolling(selected, fresh)
    }, 5000)
    return () => clearInterval(timer)
    // refreshCvStatus / ensureCvPolling stables, volontairement hors deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, backendOk, cvPreparing])

  // L'approbation vit dans metadata.json, pas dans l'index statique : elle est
  // toujours relue au serveur pour ne jamais afficher une autorisation périmée.
  const refreshApproval = async (id) => {
    if (!id || !backendOk) return
    try {
      const res = await fetch(`/api/applications/${id}/approval`, { cache: 'no-store' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const state = await res.json()
      setApprovals(prev => ({ ...prev, [id]: state }))
      setRecipientDrafts(prev => ({
        ...prev,
        [id]: { ...(prev[id] || {}), items: state.recipients || [] },
      }))
    } catch {
      setApprovals(prev => ({ ...prev, [id]: null }))
    }
  }

  useEffect(() => {
    if (!selected) return
    const timeout = setTimeout(() => refreshApproval(selected), 0)
    return () => clearTimeout(timeout)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, backendOk])

  // Pose ou retire l'autorisation d'envoi. N'envoie rien : l'envoi reste une
  // commande que seul l'utilisateur lance depuis un terminal.
  const handleApproval = async (id, approved) => {
    setApprovalPendingId(id)
    setApiError(null)
    try {
      const res = await fetch(`/api/applications/${id}/approval`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved }),
      })
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload.error || `HTTP ${res.status}`)
      setApprovals(prev => ({ ...prev, [id]: payload }))
      if (payload.recipients) {
        setRecipientDrafts(prev => ({ ...prev, [id]: { ...(prev[id] || {}), items: payload.recipients } }))
      }
    } catch (err) {
      setApiError(err.message || "Impossible d'enregistrer l'approbation.")
    } finally {
      setApprovalPendingId(null)
    }
  }

  // Envoi réel via Brevo : le clic est le verrou humain ; la chaîne Python
  // re-vérifie adresse, CV et tracker avant de partir. Un seul envoi/dossier.
  const handleSendBrevo = async (id, recipients) => {
    const to = recipients.find(item => item.role === 'to')?.email || recipients[0]?.email
    const cc = recipients.filter(item => item.role === 'cc').map(item => item.email)
    if (!to) return
    const destination = cc.length ? `${to} (Cc : ${cc.join(', ')})` : to
    if (!window.confirm(`Envoyer la candidature à ${destination} ? CV + lettre en pièces jointes — un seul envoi possible.`)) return
    setSendBrevo(prev => ({ ...prev, [id]: { pending: true } }))
    setApiError(null)
    try {
      const res = await fetch(`/api/applications/${id}/send`, { method: 'POST' })
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload.refusal || payload.error || `HTTP ${res.status}`)
      setSendBrevo(prev => ({ ...prev, [id]: { pending: false, ok: true, to: payload.would_send?.to, cc: payload.would_send?.cc || [] } }))
    } catch (err) {
      setSendBrevo(prev => ({ ...prev, [id]: { pending: false, error: err.message || 'Envoi impossible.' } }))
    }
  }

  const saveRecipients = async (id) => {
    const items = recipientDrafts[id]?.items || []
    setRecipientDrafts(prev => ({ ...prev, [id]: { ...prev[id], pending: true, error: null } }))
    try {
      const res = await fetch(`/api/applications/${id}/recipients`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ recipients: items }),
      })
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload.error || `HTTP ${res.status}`)
      setRecipientDrafts(prev => ({ ...prev, [id]: { ...prev[id], items: payload.recipients || items, pending: false, saved: true } }))
      await refreshApproval(id)
    } catch (err) {
      setRecipientDrafts(prev => ({ ...prev, [id]: { ...prev[id], pending: false, error: err.message || 'Enregistrement impossible.' } }))
    }
  }

  const updateRecipient = (id, index, field, value) => {
    setRecipientDrafts(prev => {
      const items = [...(prev[id]?.items || [])]
      items[index] = { ...items[index], [field]: field === 'email' ? value : value }
      return { ...prev, [id]: { ...prev[id], items, saved: false } }
    })
  }

  const addRecipient = (id) => {
    const draft = recipientDrafts[id] || {}
    const value = (draft.value || '').trim().toLowerCase()
    if (!value || (draft.items || []).length >= 5) return
    setRecipientDrafts(prev => ({
      ...prev,
      [id]: { ...prev[id], items: [...(prev[id]?.items || []), { email: value, role: 'cc', source: 'ajout_manuel' }], value: '', saved: false },
    }))
  }

  const removeRecipient = (id, index) => {
    setRecipientDrafts(prev => {
      const items = [...(prev[id]?.items || [])]
      if (items.length <= 1) return prev
      const removed = items.splice(index, 1)[0]
      if (removed?.role === 'to' && items.length) items[0] = { ...items[0], role: 'to' }
      return { ...prev, [id]: { ...prev[id], items, saved: false } }
    })
  }

  // Régénère le PDF de la lettre depuis le markdown édité à la main.
  const handleRegenLettre = async (id) => {
    setLettreRegen(prev => ({ ...prev, [id]: { pending: true } }))
    try {
      const res = await fetch(`/api/applications/${id}/lettre/regenerate`, { method: 'POST' })
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload.error || `HTTP ${res.status}`)
      setLettreRegen(prev => ({ ...prev, [id]: { pending: false, ok: true } }))
    } catch (err) {
      setLettreRegen(prev => ({ ...prev, [id]: { pending: false, error: err.message || 'Régénération impossible.' } }))
    }
  }

  // Enregistre depuis l'éditeur de la page : le fichier du dossier est mis à
  // jour (la lettre regénère son PDF) — c'est cette version qui part à l'envoi.
  const saveDoc = async (id, kind) => {
    const setter = kind === 'lettre' ? setEditLettre : setEditMail
    const current = (kind === 'lettre' ? editLettre : editMail)[id] || {}
    setter(prev => ({ ...prev, [id]: { ...prev[id], pending: true, error: null } }))
    try {
      const res = await fetch(`/api/applications/${id}/doc/${kind}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ contenu: current.value ?? '' }),
      })
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload.error || `HTTP ${res.status}`)
      setter(prev => ({ ...prev, [id]: { ...prev[id], editing: false, pending: false, saved: true } }))
    } catch (err) {
      setter(prev => ({ ...prev, [id]: { ...prev[id], pending: false, error: err.message || 'Enregistrement impossible.' } }))
    }
  }

  // Préremplit les recommandations agent depuis le dossier sélectionné
  // (sans écraser une édition locale en cours).
  useEffect(() => {
    if (!selected || !backendOk) return
    let cancelled = false
    fetch(`/api/applications/${selected}/recommandations`)
      .then(r => r.json())
      .then(d => {
        if (!cancelled && typeof d?.recommandations === 'string') {
          setCvReco(prev => (prev[selected] !== undefined ? prev : { ...prev, [selected]: d.recommandations }))
        }
      })
      .catch(() => {})
    return () => { cancelled = true }
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
    const cvState = cvPublicationStatus(cvStatus)
    const cvProgress = cvStatus?.progress || null
    const cvBlocksSending = cvState === 'review' || cvState === 'blocked' 
    const cvReview = cvStatus?.review
    const approval = approvals[selected]
    const approvalPending = approvalPendingId === selected
    const recipientItems = recipientDrafts[selected]?.items || approval?.recipients || []
    const hasRecipients = recipientItems.length > 0
    const recipientSaved = recipientDrafts[selected]?.saved !== false
    const hasSendAttempt = Boolean(sendBrevo[selected]?.ok)
    const preuvesSuffisantes = Boolean(c?.preuves)
    return (
      <div className="candidature-detail">
        <button className="tab back-btn" onClick={() => setSelected(null)}><ArrowLeft /> Retour</button>
        <h1><FileText /> Lettre de motivation</h1>
        <div className="candidature-meta">
          <span><strong>{c?.entreprise}</strong></span>
          <span><Briefcase /> {c?.poste}</span>
          <span><Calendar /> {c?.date}</span>
        </div>

        <PreuvesPanel preuves={c?.preuves} />

        {/* Autorisation d'envoi. Distincte de « J'ai postulé » : celle-ci ouvre
            la porte, l'autre constate un envoi déjà fait. */}
        {c?.preuves && backendOk && (
          <div className="approval-zone">
            <div className="recipient-editor">
              <div className="recipient-editor-head">
                <strong>Destinataires de l'envoi</strong>
                <span>{recipientItems.length}/5</span>
              </div>
              {recipientItems.map((item, index) => (
                <div className="recipient-row" key={`${item.email}-${index}`}>
                  <select
                    value={item.role}
                    onChange={e => updateRecipient(selected, index, 'role', e.target.value)}
                    aria-label={`Rôle du destinataire ${index + 1}`}
                  >
                    <option value="to">To</option>
                    <option value="cc">Cc</option>
                  </select>
                  <input
                    type="email"
                    value={item.email}
                    onChange={e => updateRecipient(selected, index, 'email', e.target.value)}
                    aria-label={`Email du destinataire ${index + 1}`}
                  />
                  <button type="button" className="annuler-btn" onClick={() => removeRecipient(selected, index)} disabled={recipientItems.length <= 1 || hasSendAttempt}>Supprimer</button>
                </div>
              ))}
              <div className="recipient-add-row">
                <input
                  type="email"
                  placeholder="Ajouter une adresse en Cc"
                  value={recipientDrafts[selected]?.value || ''}
                  onChange={e => setRecipientDrafts(prev => ({ ...prev, [selected]: { ...prev[selected], value: e.target.value } }))}
                  disabled={recipientItems.length >= 5 || hasSendAttempt}
                />
                <button type="button" className="annuler-btn" onClick={() => addRecipient(selected)} disabled={recipientItems.length >= 5 || hasSendAttempt}>Ajouter</button>
              </div>
              <button type="button" className="approve-btn" onClick={() => saveRecipients(selected)} disabled={recipientDrafts[selected]?.pending || hasSendAttempt || !hasRecipients}>
                {recipientDrafts[selected]?.pending ? 'Enregistrement…' : 'Enregistrer les destinataires'}
              </button>
              {recipientDrafts[selected]?.error && <p className="approval-note" style={{ color: '#fb7185' }}>{recipientDrafts[selected].error}</p>}
              {!recipientSaved && <p className="approval-note">La liste a changé : enregistre-la puis réapprouve l'envoi.</p>}
            </div>
            {approval?.approved ? (
              <>
                <span className="badge-approved"><ShieldCheck /> Envoi approuvé</span>
                <button
                  type="button"
                  className="annuler-btn"
                  onClick={() => handleApproval(selected, false)}
                  disabled={approvalPending}
                >
                  {approvalPending ? '…' : "Retirer l'approbation"}
                </button>
              </>
            ) : (
              <button
                type="button"
                className="approve-btn"
                onClick={() => handleApproval(selected, true)}
                disabled={approvalPending || !preuvesSuffisantes || !hasRecipients || !recipientSaved || cvBlocksSending}
              >
                {approvalPending ? 'Enregistrement…' : <><ShieldCheck /> Approuver l'envoi</>}
              </button>
            )}
            {hasRecipients && backendOk && (
              <div className="send-brevo-zone">
                {sendBrevo[selected]?.ok ? (
                  <span className="badge-approved"><CircleCheck /> Envoyé à {sendBrevo[selected].to}{sendBrevo[selected].cc?.length ? ` · Cc : ${sendBrevo[selected].cc.join(', ')}` : ''}</span>
                ) : (
                  <button
                    type="button"
                    className="approve-btn"
                    onClick={() => handleSendBrevo(selected, recipientItems)}
                    disabled={sendBrevo[selected]?.pending || !approval?.approved || !recipientSaved || cvBlocksSending || hasSendAttempt}
                  >
                    {sendBrevo[selected]?.pending ? 'Envoi…' : <><Mail /> Envoyer par email</>}
                  </button>
                )}
                {sendBrevo[selected]?.error && (
                  <p className="approval-note" style={{ color: '#fb7185' }}>{sendBrevo[selected].error}</p>
                )}
              </div>
            )}
            <p className="approval-note">
              {hasRecipients
                ? <>L'approbation n'envoie rien : l'envoi réel part du bouton « Envoyer par email » (Brevo, un seul envoi par dossier).</>
                : "Ajoute au moins une adresse, puis enregistre-la avant d'approuver l'envoi."}
            </p>
          </div>
        )}

        {/* Bouton / badge postulé dans la vue détail */}
        <div className="postule-zone">
          {!backendOk && (
            <span className="postule-offline"><TriangleAlert /> Backend indisponible — statut non sauvegardé</span>
          )}
          {backendOk && s?.status === 'applied' ? (
            <div className="postule-applied">
              <span className="badge-applied"><CircleCheck /> Postulé le {fmtDate(s.applied_at)} · relance le {fmtShort(s.follow_up_at)}</span>
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
              disabled={pendingId === selected || cvBlocksSending}
              title={cvBlocksSending ? "Le CV de cette candidature n'est pas validé." : undefined}
            >
              {pendingId === selected ? 'En cours…' : <><CircleCheck /> J'ai postulé</>}
            </button>
          ) : null}
          {apiError && <span className="postule-error">{apiError}</span>}
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button className="copy-btn" onClick={() => copyLettre(c?.lettre || '')}>
            {copied ? <><Check /> Copié !</> : <><Clipboard /> Copier la lettre</>}
          </button>
          <button
            className="copy-btn"
            onClick={() => {
              const st = editLettre[selected] || {}
              setEditLettre(prev => ({ ...prev, [selected]: { ...st, editing: !st.editing, value: st.value ?? c?.lettre ?? '' } }))
            }}
          >
            <PenLine /> {editLettre[selected]?.editing ? "Fermer l'éditeur" : 'Modifier la lettre'}
          </button>
          {c?.metadata?.files?.motivation_letter_pdf && (
            <>
              <a className="download-btn" href={`/api/applications/${selected}/lettre/download`} download>
                <FileDown /> Lettre PDF
              </a>
              <button
                type="button"
                className="copy-btn"
                onClick={() => handleRegenLettre(selected)}
                disabled={lettreRegen[selected]?.pending}
                title="Régénère le PDF depuis lettre_motivation.md (édition hors interface)"
              >
                {lettreRegen[selected]?.pending ? '…' : lettreRegen[selected]?.ok
                  ? <><CircleCheck /> PDF à jour</>
                  : <><RotateCw /> Régénérer le PDF</>}
              </button>
            </>
          )}
        </div>
        {editLettre[selected]?.editing && (
          <>
            <textarea
              value={editLettre[selected]?.value || ''}
              onChange={e => setEditLettre(prev => ({ ...prev, [selected]: { ...prev[selected], value: e.target.value } }))}
              rows={16}
              style={{ width: '100%', marginTop: '0.5rem', fontFamily: 'inherit', fontSize: '0.9rem', lineHeight: 1.5, padding: '0.6rem', border: '1px solid var(--border-strong)', borderRadius: 6, background: 'var(--surface)' }}
            />
            <div style={{ display: 'flex', gap: '0.5rem', margin: '0.5rem 0' }}>
              <button
                className="prepare-btn"
                onClick={() => saveDoc(selected, 'lettre')}
                disabled={editLettre[selected]?.pending || !(editLettre[selected]?.value || '').trim()}
              >
                {editLettre[selected]?.pending ? 'Enregistrement…' : 'Enregistrer & régénérer le PDF'}
              </button>
              <button className="annuler-btn" onClick={() => setEditLettre(prev => ({ ...prev, [selected]: { ...prev[selected], editing: false } }))}>
                Annuler
              </button>
            </div>
          </>
        )}
        {editLettre[selected]?.saved && !editLettre[selected]?.editing && (
          <p className="approval-note" style={{ color: '#0F6E66' }}><CircleCheck /> Lettre enregistrée — PDF régénéré depuis ta version.</p>
        )}
        {editLettre[selected]?.error && (
          <p className="approval-note" style={{ color: '#fb7185' }}>{editLettre[selected].error}</p>
        )}
        <pre className="lettre-content">{editLettre[selected]?.value ?? c?.lettre}</pre>
        {c?.mail && (
          <>
            <h2><Mail /> Email de candidature</h2>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <button className="copy-btn" onClick={() => copyLettre(c?.mail || '')}>
                {copied ? <><Check /> Copié !</> : <><Clipboard /> Copier l'email</>}
              </button>
              <button
                className="copy-btn"
                onClick={() => {
                  const st = editMail[selected] || {}
                  setEditMail(prev => ({ ...prev, [selected]: { ...st, editing: !st.editing, value: st.value ?? c?.mail ?? '' } }))
                }}
              >
                <PenLine /> {editMail[selected]?.editing ? "Fermer l'éditeur" : "Modifier l'email"}
              </button>
            </div>
            {editMail[selected]?.editing && (
              <>
                <textarea
                  value={editMail[selected]?.value || ''}
                  onChange={e => setEditMail(prev => ({ ...prev, [selected]: { ...prev[selected], value: e.target.value } }))}
                  rows={12}
                  style={{ width: '100%', marginTop: '0.5rem', fontFamily: 'inherit', fontSize: '0.9rem', lineHeight: 1.5, padding: '0.6rem', border: '1px solid var(--border-strong)', borderRadius: 6, background: 'var(--surface)' }}
                />
                <div style={{ display: 'flex', gap: '0.5rem', margin: '0.5rem 0' }}>
                  <button
                    className="prepare-btn"
                    onClick={() => saveDoc(selected, 'mail')}
                    disabled={editMail[selected]?.pending || !(editMail[selected]?.value || '').trim()}
                  >
                    {editMail[selected]?.pending ? 'Enregistrement…' : 'Enregistrer le texte du mail'}
                  </button>
                  <button className="annuler-btn" onClick={() => setEditMail(prev => ({ ...prev, [selected]: { ...prev[selected], editing: false } }))}>
                    Annuler
                  </button>
                </div>
              </>
            )}
            {editMail[selected]?.saved && !editMail[selected]?.editing && (
              <p className="approval-note" style={{ color: '#0F6E66' }}><CircleCheck /> Email enregistré — c'est ce texte qui partira.</p>
            )}
            {editMail[selected]?.error && (
              <p className="approval-note" style={{ color: '#fb7185' }}>{editMail[selected].error}</p>
            )}
            <pre className="lettre-content">{editMail[selected]?.value ?? c?.mail}</pre>
          </>
        )}

        <section className="cv-generator-panel" aria-labelledby="cv-generator-title">
          <div className="cv-generator-heading">
            <h2 id="cv-generator-title"><Target /> CV personnalisé</h2>
            <span className={`cv-publication-badge ${cvState}`}>
              {CV_STATUS_LABELS[cvState] || cvState}
            </span>
          </div>
          <p className="cv-generator-help">
            La lettre est déjà prête. Générez un CV adapté uniquement si vous souhaitez en joindre un à cette candidature.
          </p>
          <textarea
            placeholder="Recommandations pour l'agent IA — ex. : « valoriser WordPress, WooCommerce et l'accessibilité RGAA », « rester sur une page », « expérience freelance 2023 → aujourd'hui »…"
            value={cvReco[selected] ?? ''}
            onChange={e => setCvReco(prev => ({ ...prev, [selected]: e.target.value }))}
            rows={3}
            style={{ width: '100%', marginBottom: '0.5rem', fontFamily: 'inherit', fontSize: '0.85rem', padding: '0.6rem', border: '1px solid var(--border-strong)', borderRadius: 6, background: 'var(--surface)' }}
          />
          <div className="cv-actions">
            <button
              type="button"
              className="prepare-btn"
              onClick={() => handlePrepareCv(selected)}
              disabled={!backendOk || cvPendingId === selected}
              aria-busy={cvPendingId === selected}
            >
              {cvPendingId === selected
                ? 'Génération du CV…'
                : cvReady
                  ? <><RotateCw /> Régénérer le CV personnalisé</>
                  : <><Target /> Générer le CV personnalisé</>}
            </button>
            {cvPendingId === selected && cvProgress?.label && (
              <p className="cv-progress-line" aria-live="polite" style={{ margin: '0.25rem 0 0', fontSize: '0.8rem', color: 'var(--text-muted, #666)' }}>
                Étape {cvProgress.index}/{cvProgress.total} — {cvProgress.label}
                {cvProgress.detail ? ` · ${cvProgress.detail}` : ''}
              </p>
            )}
            {cvReady && (
              <>
                <a className="download-btn" href={cvFileUrl(selected, 'cv_final.pdf', cvStatus)} download><FileDown /> PDF design</a>
                {cvStatus?.files?.['cv_ats.pdf'] && <a className="download-btn" href={cvFileUrl(selected, 'cv_ats.pdf', cvStatus)} download><FileDown /> PDF ATS</a>}
                <a className="download-btn" href={cvFileUrl(selected, 'cv_final.html', cvStatus)} download><Globe /> Télécharger HTML</a>
                <a className="download-btn" href={cvFileUrl(selected, 'cv_final.json', cvStatus)} download>JSON</a>
              </>
            )}
            {cvBlocksSending && cvStatus?.files?.['cv_review_preview.pdf'] && (
              // L'aperçu est téléchargeable sous un nom qui interdit de le
              // confondre avec un CV validé.
              <a className="download-btn secondary" href={cvFileUrl(selected, 'cv_review_preview.pdf', cvStatus)} download>
                <FileDown /> Aperçu à corriger
              </a>
            )}
          </div>
          {cvBlocksSending && (
            <div className="cv-publication-diagnostic" role="status">
              <strong>
                {cvState === 'blocked'
                  ? "Ce CV est bloqué : un contrôle de vérité a échoué."
                  : "Ce CV demande une correction avant d'être envoyé."}
              </strong>
              {cvStatus?.reason && <p>{cvStatus.reason}</p>}
              {Number.isInteger(cvStatus?.revision_rounds) && (
                <p className="cv-publication-rounds">
                  {cvStatus.revision_rounds === 0
                    ? 'Aucune correction automatique n\'a été nécessaire.'
                    : `${cvStatus.revision_rounds} correction(s) automatique(s) déjà tentée(s).`}
                </p>
              )}
              {(cvStatus?.blocking_issues || []).length > 0 && (
                <>
                  <strong>Affirmations sans preuve dans le profil maître</strong>
                  <ul>
                    {cvStatus.blocking_issues.slice(0, 6).map((item, index) => (
                      <li key={`blocking-${index}`}>
                        <code>{item.path}</code> — {item.detail}
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {(cvStatus?.format_issues || []).length > 0 && (
                <>
                  <strong>Contraintes de mise en page restantes</strong>
                  <ul>
                    {cvStatus.format_issues.slice(0, 6).map((item, index) => (
                      <li key={`format-${index}`}>
                        <code>{item.path}</code> — {item.detail}
                      </li>
                    ))}
                  </ul>
                </>
              )}
              <p className="cv-publication-hint">
                Relancez une génération pour tenter une nouvelle correction, ou ajustez le profil maître
                si la preuve manque réellement.
              </p>
            </div>
          )}
          {!backendOk && <p className="cv-generator-note">Le backend doit être disponible pour générer le CV.</p>}
          {cvFeedback?.id === selected && (
            <div
              className={`cv-feedback ${cvFeedback.type}`}
              role={cvFeedback.type === 'error' ? 'alert' : 'status'}
              aria-live="polite"
            >
              <span>{cvFeedback.type === 'success' ? <CircleCheck /> : <TriangleAlert />} {cvFeedback.text}</span>
              {cvFeedback.type === 'success' && cvStatus?.files?.['cv_final.pdf'] && (
                <a href={cvFileUrl(selected, 'cv_final.pdf', cvStatus)} download>
                  Télécharger le PDF
                </a>
              )}
            </div>
          )}
          {cvExists(cvStatus) && <CvAssessment assessment={cvStatus?.assessment} finalReview={cvReview} />}
        </section>
      </div>
    )
  }

  // Vue liste des candidatures
  return (
    <div className="candidatures-list">
      <h1>
        {spontanee
          ? <><ShieldCheck /> Candidatures spontanées ({candidatures.length})</>
          : <><PenLine /> Candidatures préparées ({candidatures.length})</>}
      </h1>
      {spontanee && (
        <p className="liste-intro">
          Dossiers construits sans annonce. Chacun porte les preuves qui justifient
          l'envoi : ouvre-le pour les relire avant d'approuver.
        </p>
      )}

      {!backendOk && (
        <div className="backend-warning">
          <TriangleAlert /> Serveur backend indisponible — les statuts ne peuvent pas être enregistrés.
          Lance <code>cd server &amp;&amp; npm start</code> pour activer la persistance.
        </div>
      )}

      {apiError && (
        <div className="backend-warning">{apiError}</div>
      )}

      {candidatures.length === 0 && (
        <div className="empty-state">
          {spontanee ? (
            <>
              <p>
                Aucune candidature spontanée préparée. La prospection se pilote par
                Hermes, qui mesure les entreprises de <code>config/companies.yaml</code> :
                demande <strong>company_top</strong> pour les mesurer, puis{' '}
                <strong>company_prepare</strong> pour construire le dossier retenu.
              </p>
              <p className="empty-fallback">Hermes indisponible ? Les mêmes étapes au terminal :</p>
              <ol className="empty-steps">
                <li>
                  <code>python3 -m hermes_commands.company_top --refresh</code>
                </li>
                <li>
                  <code>python3 -m hermes_commands.company_prepare X</code>
                </li>
              </ol>
              <p>Le dossier apparaît ici dès la seconde étape terminée.</p>
            </>
          ) : (
            <p>Aucune candidature préparée. Demande "prépare candidature n°X".</p>
          )}
        </div>
      )}

      {candidatures.map(c => {
        const s = statuts[c.id]
        const isApplied = s?.status === 'applied'
        const isPending = pendingId === c.id

        return (
          <article key={c.id} className={`job-card clickable postuler ${isApplied ? 'is-applied' : ''}`} onClick={() => setSelected(c.id)}>
            <div className="card-top">
              <div className="card-badges">
                {isApplied
                  ? <span className="badge-applied-small"><CircleCheck /> Postulé</span>
                  : <span className="badge-postuler">PRÊTE</span>
                }
              </div>
            </div>
            <div className="job-header">
              <h3>{c.poste}</h3>
              <p className="job-company">{c.entreprise}</p>
            </div>
            <div className="job-meta">
              <span><Calendar /> {c.date}</span>
              {isApplied && s.applied_at && (
                <span className="meta-applied">
                  Postulé le {fmtDate(s.applied_at)} · relance le {fmtShort(s.follow_up_at)}
                </span>
              )}
            </div>
            <p className="job-excerpt">
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
                  {isPending ? 'En cours…' : <><CircleCheck /> J'ai postulé</>}
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
        <button className="tab back-btn" onClick={() => setSelected(null)}><ArrowLeft /> Retour</button>
        <h1><CircleCheck /> Candidature postulée</h1>
        <div className="candidature-meta">
          <span><strong>{c?.entreprise}</strong></span>
          <span><Briefcase /> {c?.poste}</span>
          <span><Calendar /> Postulé le {fmtDate(c?.applied_at)}</span>
          <span>
            <Bell /> Relance le {fmtDate(c?.follow_up_at)}
            {isDue && <span className="badge-relance-due"><AlarmClock /> À relancer !</span>}
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
            <h2><FileText /> Lettre de motivation</h2>
            <button className="copy-btn" onClick={() => copyLettre(c.lettre)}>
              {copied ? <><Check /> Copié !</> : <><Clipboard /> Copier la lettre</>}
            </button>
            <pre className="lettre-content">{c.lettre}</pre>
          </>
        )}
        {c?.mail && (
          <>
            <h2><Mail /> Email de candidature</h2>
            <button className="copy-btn" onClick={() => copyLettre(c.mail)}>
              {copied ? <><Check /> Copié !</> : <><Clipboard /> Copier l'email</>}
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
        <h1><CircleCheck /> Candidatures postulées</h1>
        <div className="backend-warning">
          <TriangleAlert /> Serveur backend indisponible — impossible de charger les candidatures postulées.
          Lance <code>cd server &amp;&amp; npm start</code> pour activer la persistance.
        </div>
      </div>
    )
  }

  return (
    <div className="candidatures-list">
      <h1><CircleCheck /> Candidatures postulées ({postulees.length})</h1>

      {apiError && <div className="backend-warning">{apiError}</div>}

      {postulees.length === 0 && (
        <div className="empty-state">
          <p>
            Aucune candidature postulée pour l'instant.<br />
            Va dans <PenLine /> Candidatures et clique « <CircleCheck /> J'ai postulé ».
          </p>
        </div>
      )}

      {postulees.map(p => {
        const isDue = p.follow_up_at && p.follow_up_at <= today
        const isPending = pendingId === p.id
        return (
          <article
            key={p.id}
            className="job-card clickable is-applied"
            onClick={() => setSelected(p.id)}
          >
            <div className="card-top">
              <div className="card-badges">
                {isDue
                  ? <span className="badge-relance-due"><AlarmClock /> À relancer !</span>
                  : <span className="badge-applied-small"><CircleCheck /> Postulé</span>
                }
              </div>
            </div>
            <div className="job-header">
              <h3>{p.poste}</h3>
              <p className="job-company">{p.entreprise}</p>
            </div>
            <div className="job-meta">
              <span><Calendar /> Postulé le {fmtDate(p.applied_at)}</span>
              <span><Bell /> Relance le {fmtDate(p.follow_up_at)}</span>
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

function distanceLabel(agency) {
  if (agency.distance_m == null) {
    return agency.address || 'Distance non calculée (adresse non publiée sur le site)'
  }
  const d = agency.distance_m < 1000
    ? `${agency.distance_m} m`
    : `${(agency.distance_m / 1000).toFixed(1).replace('.', ',')} km`
  const approx = (agency.address_source || '').startsWith('~') ? ' (approx.)' : ''
  return `${d} de la Monte-Cristo${approx}${agency.address ? ` — ${agency.address}` : ''}`
}

const AGENCY_TARGET_STORAGE_KEY = 'job-search:active-agency-target'

// Le ciblage « Retenir & préparer » est asynchrone : son task_id est persisté
// pour que quitter l'onglet (voire fermer la fenêtre) ne rende pas le suivi
// muet. Le serveur, lui, continue toujours le travail.
function readAgencyTargetTask() {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(AGENCY_TARGET_STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function writeAgencyTargetTask(entry) {
  if (typeof window === 'undefined' || !entry?.taskId) return
  try {
    window.localStorage.setItem(AGENCY_TARGET_STORAGE_KEY, JSON.stringify(entry))
  } catch {
    /* mode privé : le suivi marche quand même pendant la session */
  }
}

function clearAgencyTargetTask() {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(AGENCY_TARGET_STORAGE_KEY)
  } catch {
    /* rien à faire */
  }
}

const AGENCY_SEARCH_STORAGE_KEY = 'job-search:selected-agency-search'

// Le sélecteur mémorise la recherche consultée : revenir sur l'onglet ne doit
// pas rebasculer silencieusement sur une autre ville que celle qu'on lisait.
function storedSearchId() {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage.getItem(AGENCY_SEARCH_STORAGE_KEY) || null
  } catch {
    return null
  }
}

function rememberSearchId(searchId) {
  if (typeof window === 'undefined' || !searchId) return
  try {
    window.localStorage.setItem(AGENCY_SEARCH_STORAGE_KEY, searchId)
  } catch {
    /* mode privé : le sélecteur marche quand même, il n'est juste pas mémorisé */
  }
}

function searchOptionLabel(search) {
  const place = search.zone_label || search.zone || search.search_id
  const date = (search.generated_at || '').replace('T', ' ').slice(0, 16)
  const radius = search.radius_m ? ` · ${(search.radius_m / 1000).toFixed(1).replace('.', ',')} km` : ''
  const empty = search.state === 'vide' ? ' · aucun résultat' : ''
  return `${place}${date ? ` — ${date}` : ''}${radius}${empty}`
}

function domainOf(website) {
  if (!website) return null
  try {
    return new URL(website).hostname.replace(/^www\./, '')
  } catch {
    return null
  }
}

// Le bloc `analysis` du snapshot fait foi : il a été figé avec la recherche.
// L'analyse persistée ne sert qu'à combler une recherche antérieure à la phase 2,
// et son état (courant / obsolète) reste affiché tel quel — jamais requalifié.
function analysisOf(agency, persisted) {
  const domain = domainOf(agency.website)
  const embedded = agency.analysis && typeof agency.analysis === 'object' ? agency.analysis : null
  if (embedded) {
    return { ...embedded, origin: 'recherche', obsolete: false, domain }
  }
  const stored = domain ? persisted?.[domain] : null
  if (!stored) return null
  return {
    ...stored,
    fit_status: stored.status,
    origin: 'analyse persistée',
    obsolete: stored.obsolete === true,
  }
}

function AgencyAnalysisBlock({ analysis }) {
  if (!analysis) return null
  const ok = (analysis.fit_status || analysis.status) === 'ok'
  return (
    <div className="job-points agency-analysis">
      <div className="agency-analysis-head">
        <strong>{ok ? 'Analyse d’adéquation' : 'Analyse à revoir'}</strong>
        <span className="agency-analysis-tags">
          {ok && analysis.fit_score != null && <span className="agency-tag">{analysis.fit_score}/10</span>}
          {analysis.confidence && <span className="agency-tag">confiance {analysis.confidence}</span>}
          {analysis.origin && <span className="agency-tag muted">{analysis.origin}</span>}
          {analysis.obsolete && <span className="agency-tag warn">obsolète</span>}
          {analysis.analyzed_at && (
            <span className="agency-tag muted">{String(analysis.analyzed_at).replace('T', ' ').slice(0, 16)}</span>
          )}
        </span>
      </div>
      {analysis.fit_summary && <p className="agency-analysis-summary">{analysis.fit_summary}</p>}
      {analysis.strengths?.length > 0 && (
        <ul>{analysis.strengths.map((f, idx) => <li key={`s${idx}`}>✅ {f}</li>)}</ul>
      )}
      {analysis.weaknesses?.length > 0 && (
        <ul>{analysis.weaknesses.map((f, idx) => <li key={`w${idx}`}>⚠️ {f}</li>)}</ul>
      )}
      {analysis.application_angle && (
        <p className="agency-analysis-angle"><Target /> {analysis.application_angle}</p>
      )}
      {analysis.evidence_urls?.length > 0 && (
        <p className="agency-analysis-evidence">
          Preuves :{' '}
          {analysis.evidence_urls.slice(0, 4).map((url, idx) => (
            <a key={idx} href={url} target="_blank" rel="noopener noreferrer">{url.replace(/^https?:\/\//, '').slice(0, 42)}</a>
          ))}
        </p>
      )}
      {!ok && analysis.issues?.length > 0 && (
        <p className="agency-analysis-issues">Non concluant : {analysis.issues.join(' · ')}</p>
      )}
    </div>
  )
}

function AgenciesView() {
  const [index, setIndex] = useState(null)
  const [selectedId, setSelectedId] = useState(() => storedSearchId())
  const [payload, setPayload] = useState(null)
  const [persisted, setPersisted] = useState({})
  const [fetchError, setFetchError] = useState(null)
  const [categoryFilter, setCategoryFilter] = useState('agence') // toutes | agence | formation | incertain | ecarte
  const [targetingState, setTargetingState] = useState({}) // { [domain]: { pending, done, error } }
  const latestSearchRef = useRef(null)

  // 1) L'index d'abord : c'est lui qui dit quelles recherches existent.
  // Repli sur le fichier statique puis sur `latest.json` — une installation
  // antérieure à la phase 3 n'a ni route ni index, et doit rester utilisable.
  // L'index est relu périodiquement : une prospection lancée par Hermes peut se
  // terminer pendant que cet écran reste ouvert.
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      const stamp = Date.now()
      for (const url of ['/api/agencies/searches', `${DATA_URL}/agencies/index.json?t=${stamp}`]) {
        try {
          const res = await fetch(url, { cache: 'no-store' })
          if (!res.ok) continue
          const data = await res.json()
          if (Array.isArray(data?.searches) && data.searches.length > 0) {
            if (!cancelled) {
              const latestId = data.latest_search_id || data.searches[0]?.search_id
              const changed = latestId && latestId !== latestSearchRef.current
              latestSearchRef.current = latestId || null
              setIndex(data)
              if (changed) setSelectedId(latestId)
              setFetchError(null)
            }
            return
          }
        } catch {
          /* source suivante */
        }
      }
      // Ni route ni index : on tente l'alias de compatibilité seul.
      try {
        const res = await fetch(`${DATA_URL}/agencies/latest.json?t=${stamp}`, { cache: 'no-store' })
        if (!res.ok) throw new Error(String(res.status))
        const latest = await res.json()
        if (cancelled) return
        const fallbackIndex = {
          source: 'latest',
          latest_search_id: latest.search_id || 'latest',
          searches: [{
            search_id: latest.search_id || 'latest',
            zone: latest.zone,
            zone_label: latest.zone_label,
            generated_at: latest.generated_at,
            radius_m: latest.radius?.radius_m ?? null,
            total: (latest.agencies || []).length,
            state: 'ok',
          }],
        }
        const latestId = fallbackIndex.latest_search_id
        const changed = latestId !== latestSearchRef.current
        latestSearchRef.current = latestId
        setIndex(fallbackIndex)
        if (changed) setSelectedId(latestId)
      } catch {
        if (!cancelled) setFetchError('Données agences non disponibles. Lance "lance prospection agences web".')
      }
    }
    load()
    const refresh = window.setInterval(load, 15000)
    return () => {
      cancelled = true
      window.clearInterval(refresh)
    }
  }, [])

  // 2) La recherche à afficher : celle mémorisée si elle existe encore,
  // sinon la dernière passe valide.
  useEffect(() => {
    if (!index?.searches?.length) return
    const known = index.searches.map(s => s.search_id)
    setSelectedId(current => {
      if (current && known.includes(current)) return current
      const firstOk = index.searches.find(s => s.state !== 'vide')
      return index.latest_search_id && known.includes(index.latest_search_id)
        ? index.latest_search_id
        : (firstOk?.search_id || known[0])
    })
  }, [index])

  // 3) Les résultats de la recherche sélectionnée.
  useEffect(() => {
    if (!selectedId) return
    let cancelled = false
    rememberSearchId(selectedId)
    const entry = index?.searches?.find(s => s.search_id === selectedId)
    const staticUrl = entry?.file
      ? `${DATA_URL}/agencies/${entry.file}`
      : `${DATA_URL}/agencies/latest.json`

    const load = async () => {
      for (const url of [`/api/agencies/searches/${encodeURIComponent(selectedId)}`, staticUrl]) {
        try {
          const requestUrl = url.includes('/api/') ? url : `${url}${url.includes('?') ? '&' : '?'}t=${Date.now()}`
          const res = await fetch(requestUrl, { cache: 'no-store' })
          if (!res.ok) continue
          const data = await res.json()
          if (cancelled) return
          setPayload(data)
          setFetchError(null)
          return
        } catch {
          /* source suivante */
        }
      }
      if (!cancelled) {
        setPayload(null)
        setFetchError(`Recherche « ${selectedId} » illisible.`)
      }
    }
    load()
    return () => { cancelled = true }
  }, [selectedId, index])

  // 4) Analyses persistées : elles survivent aux runs, et comblent les
  // recherches produites avant la phase 2. Leur absence n'est pas une erreur.
  useEffect(() => {
    fetch('/api/agencies/analyses', { cache: 'no-store' })
      .then(r => (r.ok ? r.json() : null))
      .then(data => setPersisted(data?.analyses || {}))
      .catch(() => setPersisted({}))
  }, [])

  const searches = index?.searches || []
  const selected = searches.find(s => s.search_id === selectedId) || null
  // Les anciens snapshots peuvent encore contenir des lignes injectées depuis
  // config/companies.csv sans découverte pendant la passe. Elles restent dans
  // l'archive historique, mais ne sont plus présentées comme des résultats.
  const allAgencies = (payload?.agencies || []).filter(agency => {
    const origins = agency.origins || [agency.origin].filter(Boolean)
    return !(origins.length === 1 && origins[0] === 'csv')
  })
  const agencies = categoryFilter === 'toutes'
    ? allAgencies
    : allAgencies.filter(a => (a.category || 'agence') === categoryFilter)
  const counts = {
    agence: allAgencies.filter(a => (a.category || 'agence') === 'agence').length,
    formation: allAgencies.filter(a => a.category === 'formation').length,
    incertain: allAgencies.filter(a => a.category === 'incertain').length,
    ecarte: allAgencies.filter(a => a.category === 'ecarte').length,
  }
  const addressKnown = allAgencies.filter(a => ['adresse', 'contact/legales'].includes(a.how)).length
  const fit = payload?.fit_analysis || null
  const agencyCategoryLabel = (agency) => {
    if (agency.category === 'formation') return 'Organisme de formation'
    if (agency.category === 'incertain') return agency.origins?.includes('registre') ? 'Incertain — registre' : 'Incertain'
    if (agency.category === 'ecarte') return 'Écarté'
    return 'Agence'
  }
  const agencyCategoryClass = (agency) => {
    if (agency.category === 'formation') return 'badge-formation'
    if (agency.category === 'incertain') return 'badge-peut-etre'
    if (agency.category === 'ecarte') return 'badge-passer'
    return 'badge-agency'
  }
  const agencyScoreLabel = (agency) => {
    const score = agency.score
    const isUnscoredRegistry = score === 0 && agency.origins?.includes('registre') && !agency.website
    const isUnscoredManual = score === 0 && agency.sources?.includes('config/companies.csv')
    if (isUnscoredRegistry) return 'Non scoré'
    if (isUnscoredManual) return 'Cible manuelle'
    return `${score ?? '?'}/100`
  }
  // L'entrée d'index fait foi sur la géographie ; le payload sert de repli pour
  // une installation où seul `latest.json` existe.
  const geoPlace = selected?.zone_label || payload?.zone_label || payload?.zone || null
  const geoRadius = selected?.radius_m ?? payload?.radius?.radius_m ?? null
  const geoOrigin = selected?.origin || payload?.distance_origin || null
  const geoDate = selected?.generated_at || payload?.generated_at || null

  const handleTargetAgency = async (agency) => {
    if (!agency.website) return

    const domain = new URL(agency.website).hostname
    setTargetingState(prev => ({ ...prev, [domain]: { pending: true, done: false, error: null } }))

    try {
      const res = await fetch('/api/agencies/target', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // Le serveur relit l'agence dans CETTE recherche, pas dans « la dernière ».
        body: JSON.stringify({ domain, search_id: selectedId })
      })
      const payload = await res.json().catch(() => ({}))

      if (!res.ok) {
        throw new Error(payload.error || payload.reason || `HTTP ${res.status}`)
      }

      if (payload.task_id) {
        writeAgencyTargetTask({
          taskId: payload.task_id,
          domain,
          searchId: selectedId || null,
          startedAt: new Date().toISOString(),
        })
      }

      const data = payload.ok
        ? payload
        : await waitForAgencyTarget(payload.task_id, payload.status, status => {
            setTargetingState(prev => ({
              ...prev,
              [domain]: {
                pending: true,
                done: false,
                error: null,
                stage: status?.stage || 'queued',
              }
            }))
          })

      if (!data.ok) throw new Error(data.error || data.reason || 'Erreur inconnue')

      clearAgencyTargetTask()
      setTargetingState(prev => ({
        ...prev,
        [domain]: { pending: false, done: true, error: null }
      }))
    } catch (err) {
      setTargetingState(prev => ({
        ...prev,
        [domain]: {
          pending: false,
          done: false,
          error: err instanceof TypeError
            ? 'Impossible de joindre le serveur. La tâche peut continuer en arrière-plan.'
            : err.message,
        }
      }))
    }
  }

  // Reprise du ciblage au (re)montage de la vue : quitter l'onglet ne doit
  // pas rendre la préparation muette. Le serveur continue toujours le travail ;
  // ici on ne fait que réafficher sa progression — ou son résultat.
  useEffect(() => {
    const active = readAgencyTargetTask()
    if (!active?.taskId) return
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch(
          `/api/agencies/target/status/${encodeURIComponent(active.taskId)}`,
          { cache: 'no-store' }
        )
        const payload = await res.json().catch(() => ({}))
        if (cancelled) return
        if (!res.ok) {
          // Tâche inconnue (serveur redémarré) : nettoyage honnête, le résultat
          // éventuel reste vérifiable dans l'onglet Candidatures.
          clearAgencyTargetTask()
          setTargetingState(prev => ({
            ...prev,
            [active.domain]: {
              pending: false,
              done: false,
              error: 'Suivi perdu (serveur redémarré). Vérifie le résultat dans l’onglet Candidatures.',
            },
          }))
          return
        }
        if (payload.state === 'completed') {
          clearAgencyTargetTask()
          if (payload.result?.ok) {
            setTargetingState(prev => ({
              ...prev,
              [active.domain]: { pending: false, done: true, error: null },
            }))
          } else {
            setTargetingState(prev => ({
              ...prev,
              [active.domain]: { pending: false, done: false, error: 'La préparation agence est incomplète.' },
            }))
          }
          return
        }
        if (payload.state === 'failed') {
          clearAgencyTargetTask()
          setTargetingState(prev => ({
            ...prev,
            [active.domain]: {
              pending: false,
              done: false,
              error: payload.error || 'La préparation de l’agence a échoué.',
            },
          }))
          return
        }
        // queued / running : réarmer le suivi et remontrer la progression
        setTargetingState(prev => ({
          ...prev,
          [active.domain]: {
            pending: true,
            done: false,
            error: null,
            stage: payload.stage || payload.state,
          },
        }))
        await waitForAgencyTarget(active.taskId, payload, s => {
          setTargetingState(prev => ({
            ...prev,
            [active.domain]: {
              pending: true,
              done: false,
              error: null,
              stage: s?.stage || s?.state,
            },
          }))
        })
        if (cancelled) return
        clearAgencyTargetTask()
        setTargetingState(prev => ({
          ...prev,
          [active.domain]: { pending: false, done: true, error: null },
        }))
      } catch (err) {
        if (cancelled) return
        // Échec du suivi : on garde la persistance si la tâche peut encore
        // aboutir (panne réseau), on nettoie si elle est terminée en erreur.
        const failed = /échoué|incomplète/i.test(err.message || '')
        if (failed) clearAgencyTargetTask()
        setTargetingState(prev => ({
          ...prev,
          [active.domain]: { pending: false, done: false, error: err.message || 'Suivi perdu.' },
        }))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="agencies-list">
      <header className="search-header">
        <h1><Building2 /> Agences web ({agencies.length})</h1>
        <div className="stats">
          <span>Prospection hors annonces</span>
          {payload?.generated_at && <span>Dernière maj : {payload.generated_at.replace('T', ' ')}</span>}
        </div>
      </header>

      {searches.length > 0 && (
        <div className="agency-search-picker">
          <label htmlFor="agency-search-select"><Search /> Recherche</label>
          <select
            id="agency-search-select"
            value={selectedId || ''}
            onChange={e => setSelectedId(e.target.value)}
            disabled={searches.length === 1}
          >
            {searches.map(search => (
              <option key={search.search_id} value={search.search_id}>
                {searchOptionLabel(search)}
              </option>
            ))}
          </select>
          <div className="agency-search-geo">
            <span><MapPin /> {geoPlace || 'zone inconnue'}</span>
            {geoRadius && <span><Target /> rayon {geoRadius} m</span>}
            {geoOrigin && <span>depuis {geoOrigin}</span>}
            {geoDate && <span><Calendar /> {String(geoDate).replace('T', ' ').slice(0, 16)}</span>}
          </div>
          <div className="agency-search-stats">
            <span>{allAgencies.length} retenues</span>
            <span>{addressKnown} avec adresse lue</span>
            <span>{counts.agence} agences · {counts.formation} formations · {counts.incertain} incertains</span>
            {fit && (
              <span>{fit.analyzed ?? 0} analyses · {fit.cache_hits ?? 0} cache · {fit.review ?? 0} à revoir</span>
            )}
          </div>
          <div className="agency-category-filter">
            {[['agence', `Agences (${counts.agence})`],
              ['formation', `Formations (${counts.formation})`],
              ['incertain', `Incertains registre (${counts.incertain})`],
              ['toutes', `Toutes (${allAgencies.length})`]].map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={categoryFilter === value ? 'active' : ''}
                onClick={() => setCategoryFilter(value)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      {fetchError && (
        <div className="empty-state">
          <p>{fetchError}</p>
        </div>
      )}

      {!fetchError && allAgencies.length === 0 && (
        <div className="empty-state">
          <p>
            {selected?.state === 'vide'
              ? `La recherche « ${selected.zone_label || selected.zone || selected.search_id} » n'a retenu aucune agence. Les recherches précédentes restent consultables dans le sélecteur.`
              : "Aucune agence retenue pour l'instant. Relance une prospection agences web."}
          </p>
        </div>
      )}

      {!fetchError && allAgencies.length > 0 && agencies.length === 0 && (
        <div className="empty-state">
          <p>Aucune structure dans cette catégorie pour cette recherche.</p>
        </div>
      )}

      <div className="job-list">
        {agencies.map((agency, i) => {
          const domain = agency.website ? new URL(agency.website).hostname : null
          const state = domain ? targetingState[domain] : null
          const isPending = state?.pending
          const isDone = state?.done
          const error = state?.error
          const analysis = analysisOf(agency, persisted)
          const progressLabel = state?.stage === 'préparation'
            ? 'Création de la candidature et du CV en arrière-plan…'
            : state?.stage === 'mesure'
              ? 'Analyse du site en arrière-plan…'
              : 'Mise en file de la préparation…'

          return (
            <article key={agency.website || i} className="job-card agency-card">
              <div className="card-top">
                <div className="card-badges">
                  <span className={agencyCategoryClass(agency)}>{agencyCategoryLabel(agency)}</span>
                </div>
                <span className="job-score">{agencyScoreLabel(agency)}</span>
              </div>
              <div className="job-header">
                <h3>{agency.name}</h3>
              </div>
              <div className="job-meta">
                <span><MapPin /> {distanceLabel(agency)}</span>
                {/* `how` dit d'où vient la position : une approximation ne doit
                    jamais se relire comme une adresse relevée. */}
                {agency.how && <span className="agency-how">position : {agency.how}</span>}
                {/* `site_match` dit ce qui rattache ce site à cette structure.
                    Un site trouvé pour un candidat du registre et affiché sans
                    sa preuve serait une attribution incontestable. */}
                {agency.site_match && agency.site_match !== 'aucun' && (
                  <span className="agency-how" title={agency.site_match_evidence || ''}>
                    site : {agency.site_match}
                  </span>
                )}
                {agency.stack?.length > 0 && <span><Wrench /> {agency.stack.join(', ')}</span>}
                {agency.emails?.length > 0 && <span><Mail /> {agency.emails[0]}</span>}
                {agency.query && <span><Search /> {agency.query}</span>}
              </div>
              <AgencyAnalysisBlock analysis={analysis} />
              {agency.reasons?.length > 0 && (
                <div className="job-points">
                  <strong>Signaux du barème :</strong>
                  <ul>{agency.reasons.slice(0, 5).map((r, idx) => <li key={idx}>{r}</li>)}</ul>
                </div>
              )}

              {isPending && (
                <div className="agency-targeting-status loading-status">
                  <span><LoaderCircle className="spin" /> {progressLabel}</span>
                </div>
              )}
              {isDone && !error && (
                <div className="agency-targeting-status success-status">
                  <span><CircleCheck /> Dossier prêt — voir l'onglet 🛡 Spontanées</span>
                </div>
              )}
              {error && (
                <div className="agency-targeting-status error-status">
                  <span><TriangleAlert /> {error}</span>
                </div>
              )}

              <div className="agency-actions">
                {domain && (
                  <button
                    className={`prepare-btn ${isDone ? 'done' : ''}`}
                    onClick={() => handleTargetAgency(agency)}
                    disabled={isPending || isDone}
                  >
                    {isPending
                      ? <>Préparation…</>
                      : isDone
                        ? <>✅ Dossier préparé</>
                        : <>🎯 Retenir & préparer</>}
                  </button>
                )}
                {agency.website && (
                  <a href={agency.website} target="_blank" rel="noopener noreferrer" className="job-link">
                    <Globe /> Ouvrir le site
                  </a>
                )}
                {agency.contact_urls?.[0] && (
                  <a href={agency.contact_urls[0]} target="_blank" rel="noopener noreferrer" className="job-link">
                    <Send /> Contact / recrutement
                  </a>
                )}
              </div>
            </article>
          )
        })}
      </div>
    </div>
  )
}

// [composant d'icône lucide, libellé]
const WEATHER_CODES = {
  0: [Sun, 'Ciel dégagé'],
  1: [CloudSun, 'Principalement dégagé'],
  2: [CloudSun, 'Partiellement nuageux'],
  3: [Cloud, 'Couvert'],
  45: [CloudFog, 'Brouillard'],
  48: [CloudFog, 'Brouillard givrant'],
  51: [CloudDrizzle, 'Bruine faible'],
  53: [CloudDrizzle, 'Bruine modérée'],
  55: [CloudRain, 'Bruine dense'],
  61: [CloudRain, 'Pluie faible'],
  63: [CloudRain, 'Pluie modérée'],
  65: [CloudRain, 'Forte pluie'],
  71: [CloudSnow, 'Neige faible'],
  73: [CloudSnow, 'Neige modérée'],
  75: [Snowflake, 'Forte neige'],
  80: [CloudDrizzle, 'Averses faibles'],
  81: [CloudRain, 'Averses modérées'],
  82: [CloudLightning, 'Fortes averses'],
  95: [CloudLightning, 'Orage'],
  96: [CloudLightning, 'Orage avec grêle'],
  99: [CloudLightning, 'Orage violent avec grêle'],
}

function weatherLabel(code) {
  return WEATHER_CODES[code] || [Thermometer, 'Conditions inconnues']
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
    const timeout = setTimeout(() => loadWeather('Paris'), 0)
    return () => clearTimeout(timeout)
    // Chargement initial unique de la météo par défaut.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const current = weather?.current
  const [CurrentIcon, currentText] = weatherLabel(current?.weather_code)
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
        <h1><CloudSun /> Météo en direct</h1>
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
          <MapPin /> Ma position
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
              <span className="weather-icon"><CurrentIcon /></span>
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
                const [Icon, text] = weatherLabel(hour.code)
                return (
                  <article key={hour.time} className="weather-mini-card">
                    <span>{formatHour(hour.time)}</span>
                    <strong><Icon /> {Math.round(hour.temp)}°C</strong>
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
                const [Icon, text] = weatherLabel(weather.daily.weather_code[index])
                return (
                  <article key={day} className="weather-day-card">
                    <span>{formatDay(day)}</span>
                    <strong><Icon /> {text}</strong>
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

// Entrées de navigation. `primary: true` = visible dans la barre du bas sur mobile.
const NAV_ITEMS = [
  { id: 'recherche', Icon: Search, label: 'Recherches', hint: 'Offres analysées', primary: true },
  { id: 'manual-cv', Icon: Sparkles, label: 'CV', hint: 'Depuis une annonce', primary: true },
  { id: 'candidatures', Icon: PenLine, label: 'Lettres', hint: 'Réponses à une annonce', primary: true },
  { id: 'spontanees', Icon: ShieldCheck, label: 'Spontanées', hint: 'Sans annonce, à approuver' },
  { id: 'cvs', Icon: FileText, label: 'Mes CV', hint: 'CV générés', primary: false },
  { id: 'postulees', Icon: CircleCheck, label: 'Postulées', hint: 'Suivi des envois', primary: true },
  { id: 'scout', Icon: MapPin, label: 'Agences v3', hint: 'Google Places + IA' },
  { id: 'agencies', Icon: Building2, label: 'Agences', hint: 'Prospection hors annonces' },
  { id: 'weather', Icon: CloudSun, label: 'Météo', hint: 'Direct sans backend' },
]

function App() {
  const [index, setIndex] = useState(null)
  const [activeSearch, setActiveSearch] = useState(null)
  const [activeCategory, setActiveCategory] = useState('backend')
  const [activeMode, setActiveMode] = useState('recherche')  // recherche | manual-cv | cvs | agencies | candidatures | spontanees | postulees | weather
  const [nbPostulees, setNbPostulees] = useState(0)          // compteur sidebar dynamique
  const [moreOpen, setMoreOpen] = useState(false)            // feuille « Plus » (mobile)
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(false)
  const [fetchError, setFetchError] = useState(false)
  const [preparePendingKey, setPreparePendingKey] = useState(null)
  const [prepareMessage, setPrepareMessage] = useState(null)
  const { status: searchStatus, launching: searchLaunching, launch: launchSearch } = useSearchRunner()

  const loadIndex = useCallback(() => {
    return fetch(`${DATA_URL}/index.json?t=${Date.now()}`, { cache: 'no-store' })
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json() })
      .then(data => {
        setIndex(data)
        if (data.searches?.length > 0) {
          setActiveSearch(current => current || data.searches[0].id)
        }
        return data
      })
      .catch(() => console.log('Index not found yet'))
  }, [])

  useEffect(() => {
    loadIndex()
    const onFocus = () => loadIndex()
    window.addEventListener('focus', onFocus)
    const timer = window.setInterval(loadIndex, 30000)
    return () => {
      window.removeEventListener('focus', onFocus)
      window.clearInterval(timer)
    }
  }, [loadIndex])

  useEffect(() => {
    if (!searchStatus.running && searchStatus.lastResult) {
      loadIndex().then(data => {
        if (data?.searches?.length > 0) setActiveSearch(data.searches[0].id)
      })
    }
  }, [searchStatus.running, searchStatus.lastResult, loadIndex])

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
    fetch(`${DATA_URL}/${activeSearch}/${activeCategory}.json?t=${Date.now()}`, { cache: 'no-store' })
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json() })
      .then(data => setJobs(data.jobs || []))
      .catch(() => { setJobs([]); setFetchError(true) })
      .finally(() => setLoading(false))
  }, [activeSearch, activeCategory, activeMode, index])

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
      // Compat : un ancien backend répondait 201 avec la candidature directement.
      const prepared = data.id ? data : await waitForPreparation(data.task_id, data.status)
      setPrepareMessage({ type: 'success', text: `Lettre de motivation prête : ${prepared.id}` })
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

  const goTo = (mode) => {
    setActiveMode(mode)
    setMoreOpen(false)
  }

  const openSearch = (id) => {
    setActiveMode('recherche')
    setActiveSearch(id)
    setMoreOpen(false)
  }

  // Une recherche lancée depuis le chat Hermes écrit sa session dans index.json en tâche de
  // fond : on rafraîchit la liste pour que la carte apparaisse, sans changer ce que l'utilisateur
  // regarde. `onOpenSearch` (déclenché par le lien affiché dans le fil) ouvre la carte visée.
  const handleHermesSearchDone = () => { loadIndex() }
  const handleOpenSearchFromChat = (id) => { loadIndex().then(() => openSearch(id)) }

  const navHint = (item) => (
    item.id === 'postulees'
      ? (nbPostulees > 0 ? `${nbPostulees} postulées` : 'Aucune')
      : item.id === 'recherche'
        ? `${index?.searches?.length || 0} sessions`
        : item.hint
  )

  const launchLabel = searchStatus.running
    ? <><LoaderCircle className="spin" /> Recherche en cours…</>
    : searchLaunching ? 'Lancement…' : <><Rocket /> Lancer une recherche</>

  return (
    <div className="app-layout">
      <HermesChat onSearchDone={handleHermesSearchDone} onOpenSearch={handleOpenSearchFromChat} />
      <aside className="sidebar">
        <button
          className="prepare-btn launch-search-btn"
          onClick={launchSearch}
          disabled={searchLaunching || searchStatus.running}
        >
          {launchLabel}
        </button>
        {!searchStatus.running && searchStatus.lastResult && (
          <p className="last-run">
            Dernier run : {searchStatus.lastResult.total} offres
            {' · '}<span className="postuler"><Star /> {searchStatus.lastResult.postuler}</span>
            {' · '}<span className="peut-etre"><CircleDot /> {searchStatus.lastResult.peut_etre}</span>
          </p>
        )}
        {searchStatus.error && (
          <div className="backend-warning">{searchStatus.error}</div>
        )}
        <h2>Navigation</h2>
        {NAV_ITEMS.map(item => (
          <button
            key={item.id}
            className={`search-btn mode-btn ${item.id === 'manual-cv' ? 'manual-cv-nav' : ''} ${activeMode === item.id ? 'active' : ''}`}
            onClick={() => goTo(item.id)}
          >
            <span className="search-date"><item.Icon /> {item.label}</span>
            <span className="search-stats">{navHint(item)}</span>
          </button>
        ))}
        <hr className="sidebar-divider" />
        <h2>Sessions</h2>
        {index?.searches?.map(search => (
          <button
            key={search.id}
            className={`search-btn ${search.id === activeSearch && activeMode === 'recherche' ? 'active' : ''}`}
            onClick={() => openSearch(search.id)}
          >
            <span className="search-date">{fmtSession(search)}</span>
            <span className="search-stats">
              {search.found_total ?? search.total} trouvées · {search.total} nouvelles
              {search.already_seen > 0 && ` · ${search.already_seen} déjà vues`}
              {' · '}<Star /> {search.postuler}
            </span>
          </button>
        ))}
      </aside>

      <main className="main-content">
        {activeMode === 'manual-cv' ? (
          <ManualCvView onOpenCandidatures={() => setActiveMode('candidatures')} />
        ) : activeMode === 'candidatures' ? (
          <CandidaturesView key="annonce" />
        ) : activeMode === 'spontanees' ? (
          <CandidaturesView key="spontanee" mission="spontanee" />
        ) : activeMode === 'cvs' ? (
          <MesCvView />
        ) : activeMode === 'postulees' ? (
          <PostuleesView />
        ) : activeMode === 'weather' ? (
          <WeatherView />
        ) : activeMode === 'scout' ? (
          <AgencyScout />
        ) : activeMode === 'agencies' ? (
          <AgenciesView />
        ) : currentSearch ? (
          <>
            <header className="search-header">
              <h1>Recherche du {fmtSession(currentSearch)}</h1>
              <div className="stats">
                <span><Search /> {currentSearch.found_total ?? currentSearch.total} trouvées</span>
                <span>{currentSearch.total} nouvelles</span>
                {currentSearch.already_seen > 0 && (
                  <span><RotateCw /> {currentSearch.already_seen} déjà vues</span>
                )}
                <span className="postuler"><Star /> {currentSearch.postuler} POSTULER</span>
                <span className="peut-etre"><CircleDot /> {currentSearch.peut_etre} PEUT-ÊTRE</span>
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
                  {cat === 'backend' ? <><Server /> Backend</> :
                   cat === 'frontend' ? <><Palette /> Frontend</> :
                   cat === 'webmaster_formateur' ? <><GraduationCap /> Web &amp; Formateur</> :
                   cat === 'nouvelles_portes' ? <><DoorOpen /> Nouvelles Portes</> :
                   cat === 'deja_vues' ? <><RotateCw /> Déjà vues</> :
                   <><CircleDot /> Non classées</>}
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
                {jobs.map((job) => {
                  const ai = job.ai_analysis || {}
                  const reco = ai.recommandation || '?'
                  const recoClass = reco === 'POSTULER' ? 'postuler' :
                                    reco === 'PASSER' ? 'passer' : 'peut-etre'
                  const prepareKey = job.url || `${job.title}-${job.company}`
                  const isPreparing = preparePendingKey === prepareKey
                  return (
                    <article key={prepareKey} className={`job-card ${recoClass}`}>
                      <div className="card-top">
                        <div className="card-badges">
                          <span className={`badge-${recoClass}`}>{reco}</span>
                        </div>
                        {job.score != null && (
                          <span className="job-score"><strong>{job.score}</strong>/100</span>
                        )}
                      </div>
                      <div className="job-header">
                        <h3>{job.title}</h3>
                        <p className="job-company">{job.company}</p>
                      </div>
                      <div className="job-meta">
                        <span><MapPin /> {job.location}</span>
                        <span><Briefcase /> {job.contract_type || '?'}</span>
                        {job.published_at && <span><Calendar /> {job.published_at.slice(0, 10)}</span>}
                      </div>
                      {(ai.raison_breve || ai.points_forts?.length > 0 || ai.points_faibles?.length > 0) && (
                        <details className="job-analysis-details">
                          <summary>Analyse détaillée</summary>
                          {ai.raison_breve && <p className="job-analysis"><MessageCircle /> {ai.raison_breve}</p>}
                          {ai.points_forts?.length > 0 && (
                            <div className="job-points">
                              <strong>Points forts</strong>
                              <ul>{ai.points_forts.slice(0, 3).map((p, idx) => <li key={idx}>{p}</li>)}</ul>
                            </div>
                          )}
                          {ai.points_faibles?.length > 0 && (
                            <div className="job-points warning">
                              <strong>Vigilance</strong>
                              <ul>{ai.points_faibles.slice(0, 2).map((p, idx) => <li key={idx}>{p}</li>)}</ul>
                            </div>
                          )}
                        </details>
                      )}
                      <div className="prepare-actions">
                        <button
                          className="prepare-btn"
                          onClick={() => handlePrepareCandidature(job)}
                          disabled={isPreparing}
                        >
                          {isPreparing ? 'Création de la lettre…' : <><PenLine /> Créer la lettre</>}
                        </button>
                        {job.url && (
                          <a href={job.url} target="_blank" rel="noopener noreferrer" className="job-link">
                            <ExternalLink /> Voir l'offre
                          </a>
                        )}
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

      {/* Bouton flottant — équivalent mobile du bouton en tête de sidebar.
          Réservé au mode recherche : il ne lance que le scraping d'annonces, et
          ailleurs il recouvrait le contenu en proposant une action hors sujet. */}
      {activeMode === 'recherche' && (
        <button
          className="fab"
          onClick={launchSearch}
          disabled={searchLaunching || searchStatus.running}
        >
          {launchLabel}
        </button>
      )}

      {/* Barre de navigation basse — mobile uniquement */}
      <nav className="bottom-nav">
        {NAV_ITEMS.filter(item => item.primary).map(item => (
          <button
            key={item.id}
            className={`bottom-nav-item ${activeMode === item.id ? 'active' : ''}`}
            onClick={() => goTo(item.id)}
          >
            <span className="nav-icon"><item.Icon /></span>
            {item.label}
            {item.id === 'postulees' && nbPostulees > 0 && (
              <span className="nav-count">{nbPostulees}</span>
            )}
          </button>
        ))}
        <button
          className={`bottom-nav-item ${moreOpen ? 'active' : ''}`}
          onClick={() => setMoreOpen(o => !o)}
        >
          <span className="nav-icon"><Ellipsis /></span>
          Plus
        </button>
      </nav>

      {moreOpen && (
        <>
          <button
            className="more-backdrop"
            aria-label="Fermer"
            onClick={() => setMoreOpen(false)}
          />
          <div className="more-sheet">
            <h2>Autres vues</h2>
            {NAV_ITEMS.filter(item => !item.primary).map(item => (
              <button
                key={item.id}
                className={`search-btn ${activeMode === item.id ? 'active' : ''}`}
                onClick={() => goTo(item.id)}
              >
                <span className="search-date"><item.Icon /> {item.label}</span>
                <span className="search-stats">{item.hint}</span>
              </button>
            ))}
            <h2>Sessions de recherche</h2>
            {index?.searches?.length > 0 ? index.searches.map(search => (
              <button
                key={search.id}
                className={`search-btn ${search.id === activeSearch && activeMode === 'recherche' ? 'active' : ''}`}
                onClick={() => openSearch(search.id)}
              >
                <span className="search-date">{fmtSession(search)}</span>
                <span className="search-stats">
                  {search.found_total ?? search.total} trouvées · {search.total} nouvelles · <Star /> {search.postuler}
                </span>
              </button>
            )) : (
              <p className="search-stats">Aucune session pour l'instant.</p>
            )}
          </div>
        </>
      )}
    </div>
  )
}

export default App
