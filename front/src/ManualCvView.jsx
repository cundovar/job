import { useEffect, useRef, useState } from 'react'
import { FileDown, Globe, LoaderCircle, RotateCw, Sparkles, TriangleAlert } from 'lucide-react'
import CvAssessment from './CvAssessment'

const POLL_INTERVAL_MS = 2500
const GENERATION_TIMEOUT_MS = 15 * 60 * 1000
const LAST_RESULT_STORAGE_KEY = 'job-search:last-manual-cv-result'

const initialForm = {
  title: '',
  company: '',
  location: '',
  url: '',
  candidate_instructions: '',
  description: '',
}

async function readJson(response) {
  const text = await response.text()
  let payload
  try {
    payload = text ? JSON.parse(text) : {}
  } catch {
    throw new Error(`Le serveur a renvoyé une réponse invalide (HTTP ${response.status}).`)
  }
  if (!response.ok) {
    throw new Error(payload.error || `Erreur HTTP ${response.status}`)
  }
  return payload
}

function generatedCvIsComplete(status) {
  return Boolean(
    status?.files?.['cv_final.pdf'] &&
    status?.files?.['cv_ats.pdf'] &&
    status?.files?.['cv_agent_trace.json'] &&
    status?.files?.['cv_assessment.json']
  )
}

function downloadUrl(id, file) {
  return `/api/applications/${encodeURIComponent(id)}/cv/download/${file}`
}

function generationLabel(stage) {
  if (stage === 'preparing') return 'Création du dossier de candidature…'
  if (stage === 'queued') return 'CV placé dans la file de génération…'
  if (stage === 'running') return 'Les agents IA construisent et vérifient le CV…'
  if (stage === 'completed') return 'CV personnalisé terminé.'
  return ''
}

function loadLastResult() {
  if (typeof window === 'undefined') return null
  try {
    const stored = JSON.parse(window.localStorage.getItem(LAST_RESULT_STORAGE_KEY) || 'null')
    return stored?.id && stored?.status ? stored : null
  } catch {
    return null
  }
}

export default function ManualCvView({ onOpenCandidatures }) {
  const [form, setForm] = useState(initialForm)
  const [stage, setStage] = useState('idle')
  const [error, setError] = useState('')
  const [result, setResult] = useState(loadLastResult)
  const controllerRef = useRef(null)
  const isBusy = ['preparing', 'queued', 'running'].includes(stage)
  const needsRevision = result?.status?.review?.status === 'needs_revision'

  useEffect(() => () => controllerRef.current?.abort(), [])

  useEffect(() => {
    if (!result?.id || !result?.status || typeof window === 'undefined') return
    window.localStorage.setItem(LAST_RESULT_STORAGE_KEY, JSON.stringify(result))
  }, [result])

  const updateField = event => {
    const { name, value } = event.target
    setForm(previous => ({ ...previous, [name]: value }))
  }

  const waitForGeneration = async (id, signal, initialStatus) => {
    let status = initialStatus
    const deadline = Date.now() + GENERATION_TIMEOUT_MS
    let networkErrors = 0

    while (Date.now() < deadline) {
      if (status?.generation?.state === 'completed') {
        if (!generatedCvIsComplete(status)) {
          throw new Error('La génération est terminée, mais les fichiers du CV sont incomplets.')
        }
        return status
      }
      if (status?.generation?.state === 'failed') {
        throw new Error(status.generation.error || 'La génération du CV a échoué.')
      }
      if (!status?.generation) {
        throw new Error('Le serveur ne fournit plus le suivi de la génération.')
      }

      setStage(status.generation.state === 'queued' ? 'queued' : 'running')
      await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL_MS))

      try {
        const response = await fetch(`/api/applications/${encodeURIComponent(id)}/cv/status`, {
          cache: 'no-store',
          signal,
        })
        status = await readJson(response)
        networkErrors = 0
      } catch (pollError) {
        if (pollError.name === 'AbortError') throw pollError
        const isNetworkError = pollError instanceof TypeError ||
          /failed to fetch|networkerror|injoignable/i.test(pollError.message || '')
        if (!isNetworkError) throw pollError
        networkErrors += 1
        if (networkErrors >= 5) {
          throw new Error(
            'Le serveur est momentanément injoignable pendant la génération.',
            { cause: pollError }
          )
        }
      }
    }

    throw new Error('La génération dépasse 15 minutes. Vous pourrez vérifier la candidature plus tard.')
  }

  const handleSubmit = async event => {
    event.preventDefault()
    const description = form.description.trim()
    if (description.length < 80) {
      setError('Collez une annonce suffisamment complète (au moins 80 caractères).')
      return
    }

    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    setError('')
    setResult(null)
    setStage('preparing')

    const firstLine = description.split(/\r?\n/).map(line => line.trim()).find(Boolean) || ''
    const job = {
      title: form.title.trim() || firstLine.slice(0, 140) || 'Annonce personnalisée',
      company: form.company.trim() || "Entreprise de l'annonce",
      location: form.location.trim(),
      url: form.url.trim(),
      source: 'annonce_manuelle',
      contract_type: '',
      candidate_instructions: form.candidate_instructions.trim(),
      description,
    }

    try {
      const prepareResponse = await fetch('/api/applications/prepare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job }),
        signal: controller.signal,
      })
      const prepared = await readJson(prepareResponse)
      if (!prepared.id) throw new Error("L'identifiant de la candidature est absent.")

      setStage('queued')
      const generateResponse = await fetch(
        `/api/applications/${encodeURIComponent(prepared.id)}/cv/prepare`,
        { method: 'POST', signal: controller.signal }
      )
      const generation = await readJson(generateResponse)
      const finalStatus = await waitForGeneration(
        prepared.id,
        controller.signal,
        generation.status
      )

      setResult({
        id: prepared.id,
        candidature: prepared.candidature,
        status: finalStatus,
      })
      setStage('completed')
    } catch (submitError) {
      if (submitError.name === 'AbortError') return
      setStage('failed')
      setError(
        submitError instanceof TypeError
          ? 'Impossible de joindre le serveur. Vérifiez le déploiement puis réessayez.'
          : submitError.message || 'Impossible de créer le CV.'
      )
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null
    }
  }

  const handleRegenerate = async () => {
    if (!result?.id || isBusy) return
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    setError('')
    setStage('queued')
    try {
      const response = await fetch(
        `/api/applications/${encodeURIComponent(result.id)}/cv/prepare`,
        { method: 'POST', signal: controller.signal }
      )
      const generation = await readJson(response)
      const finalStatus = await waitForGeneration(result.id, controller.signal, generation.status)
      setResult(previous => ({ ...previous, status: finalStatus }))
      setStage('completed')
    } catch (regenerationError) {
      if (regenerationError.name === 'AbortError') return
      setStage('failed')
      setError(
        regenerationError instanceof TypeError
          ? 'Impossible de joindre le serveur. Vérifiez le déploiement puis réessayez.'
          : regenerationError.message || 'Impossible de régénérer le CV.'
      )
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null
    }
  }

  const handleNewCv = () => {
    controllerRef.current?.abort()
    controllerRef.current = null
    setResult(null)
    setStage('idle')
    setError('')
    setForm(initialForm)
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(LAST_RESULT_STORAGE_KEY)
    }
  }

  return (
    <div className="manual-cv-view">
      <header className="manual-cv-header">
        <span className="manual-cv-kicker">Candidature sur mesure</span>
        <h1><Sparkles /> Créer un CV depuis n’importe quelle annonce</h1>
        <p>
          Collez le texte complet. Les agents IA analysent le besoin, rédigent le CV,
          le font juger puis le révisent. Python contrôle ensuite la cohérence et produit le PDF.
        </p>
      </header>

      <form className="manual-cv-form" onSubmit={handleSubmit}>
        <div className="manual-cv-fields">
          <label>
            Intitulé du poste <span>facultatif</span>
            <input
              name="title"
              value={form.title}
              onChange={updateField}
              placeholder="Ex. Développeur full-stack"
              maxLength={160}
              disabled={isBusy}
            />
          </label>
          <label>
            Entreprise <span>facultatif</span>
            <input
              name="company"
              value={form.company}
              onChange={updateField}
              placeholder="Ex. Nom de l’entreprise"
              maxLength={160}
              disabled={isBusy}
            />
          </label>
          <label>
            Lieu <span>facultatif</span>
            <input
              name="location"
              value={form.location}
              onChange={updateField}
              placeholder="Ex. Paris, hybride"
              maxLength={160}
              disabled={isBusy}
            />
          </label>
          <label>
            Lien de l’annonce <span>facultatif</span>
            <input
              type="url"
              name="url"
              value={form.url}
              onChange={updateField}
              placeholder="https://…"
              maxLength={2000}
              disabled={isBusy}
            />
          </label>
        </div>

        <label className="manual-cv-instructions">
          Consignes personnelles pour ce CV <span>facultatif</span>
          <textarea
            name="candidate_instructions"
            value={form.candidate_instructions}
            onChange={updateField}
            placeholder="Ex. Insister sur DevDoc et le CI/CD, conserver mon expérience d’animateur, ne pas afficher une expérience précise…"
            maxLength={2000}
            rows={4}
            disabled={isBusy}
          />
          <small>
            Préférences éditoriales uniquement : elles ne permettent pas d’inventer une expérience.
          </small>
        </label>

        <label className="manual-cv-description">
          Texte complet de l’annonce <strong>obligatoire</strong>
          <textarea
            name="description"
            value={form.description}
            onChange={updateField}
            placeholder="Collez ici l’annonce complète : missions, compétences, profil recherché, contexte de l’entreprise…"
            minLength={80}
            maxLength={40000}
            rows={16}
            required
            disabled={isBusy}
          />
          <small>{form.description.length.toLocaleString('fr-FR')} / 40 000 caractères</small>
        </label>

        <div className="manual-cv-submit-row">
          <button className="prepare-btn manual-cv-submit" type="submit" disabled={isBusy}>
            {isBusy
              ? <><LoaderCircle className="spin" /> Création en cours…</>
              : <><Sparkles /> Analyser l’annonce et générer le CV</>}
          </button>
          <span>La photo du profil est ajoutée automatiquement au PDF.</span>
        </div>
      </form>

      {(isBusy || stage === 'completed') && (
        <section className="manual-cv-progress" aria-live="polite">
          <h2>
            {stage === 'completed' && needsRevision
              ? 'CV généré, mais le juge demande encore des corrections.'
              : generationLabel(stage)}
          </h2>
          <ol>
            <li className={stage !== 'idle' ? 'done' : ''}>
              <strong>1</strong><span>Dossier et données de l’annonce</span>
            </li>
            <li className={['queued', 'running', 'completed'].includes(stage) ? 'done' : ''}>
              <strong>2</strong><span>Analyse, rédaction, jugement et révision par les agents IA</span>
            </li>
            <li className={stage === 'completed' ? 'done' : stage === 'running' ? 'active' : ''}>
              <strong>3</strong><span>Contrôle Python, mise en page, photo et PDF</span>
            </li>
          </ol>
        </section>
      )}

      {error && <div className="prepare-message error manual-cv-message" role="alert"><TriangleAlert /> {error}</div>}

      {result && (
        <section className="manual-cv-result">
          <div>
            <span className="manual-cv-kicker">{needsRevision ? 'CV à corriger' : 'CV prêt'}</span>
            <h2>{result.candidature?.poste || form.title || 'CV personnalisé'}</h2>
            <p>{result.candidature?.entreprise || form.company || 'Annonce personnalisée'}</p>
          </div>
          <button type="button" className="copy-btn" onClick={handleNewCv} disabled={isBusy}>
            <Sparkles /> Créer un nouveau CV
          </button>
          <CvAssessment assessment={result.status?.assessment} finalReview={result.status?.review} />
          <div className="cv-actions">
            <button
              type="button"
              className="prepare-btn"
              onClick={handleRegenerate}
              disabled={isBusy}
            >
              {isBusy
                ? <><LoaderCircle className="spin" /> Régénération…</>
                : <><RotateCw /> Régénérer avec les corrections</>}
            </button>
            <a className="download-btn primary" href={downloadUrl(result.id, 'cv_final.pdf')} download>
              <FileDown /> {needsRevision ? 'PDF à relire' : 'PDF design'}
            </a>
            <a className="download-btn" href={downloadUrl(result.id, 'cv_ats.pdf')} download>
              <FileDown /> PDF ATS
            </a>
            <a className="download-btn" href={downloadUrl(result.id, 'cv_final.html')} download>
              <Globe /> Télécharger HTML
            </a>
            <a className="download-btn" href={downloadUrl(result.id, 'cv_final.json')} download>
              JSON
            </a>
          </div>
          <button type="button" className="copy-btn" onClick={onOpenCandidatures}>
            Ouvrir la candidature complète
          </button>
        </section>
      )}
    </div>
  )
}
