import { useState } from 'react'
import { ExternalLink, ScrollText } from 'lucide-react'

// L'annonce telle que les agents du CV et de la lettre l'ont lue (demande
// Cundo 23/10/2026 : « parfois je ne sais plus de l'annonce en détail »).
// Repliée par défaut, chargée à la première ouverture seulement.
export default function OffrePanel({ id }) {
  const [state, setState] = useState({ loaded: false, pending: false, offre: null, error: null })

  const load = async () => {
    if (state.loaded || state.pending) return
    setState(prev => ({ ...prev, pending: true }))
    try {
      const res = await fetch(`/api/applications/${encodeURIComponent(id)}/offre`)
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload.error || `Erreur ${res.status}`)
      setState({ loaded: true, pending: false, offre: payload, error: null })
    } catch (err) {
      setState({ loaded: false, pending: false, offre: null, error: err.message || 'Annonce illisible.' })
    }
  }

  const offre = state.offre
  return (
    <details className="approval-zone offre-panel" onToggle={e => e.currentTarget.open && load()}>
      <summary><ScrollText /> Voir l’annonce</summary>
      {state.pending && <p className="approval-note">Chargement…</p>}
      {state.error && <p className="approval-note" style={{ color: '#fb7185' }}>{state.error}</p>}
      {offre && (
        <>
          <p className="approval-note">
            {[offre.title, offre.company, offre.location, offre.contract_type].filter(Boolean).join(' · ')}
            {offre.url && (
              <> · <a href={offre.url} target="_blank" rel="noreferrer">annonce d’origine <ExternalLink size={12} /></a></>
            )}
          </p>
          {offre.available ? (
            <>
              <div className="offre-texte">{offre.description}</div>
              {offre.source === 'offre_resume.md' && (
                <p className="approval-note">Dossier ancien : seule la description courte avait été conservée.</p>
              )}
              {offre.truncated && <p className="approval-note">Texte très long, affiché en partie.</p>}
            </>
          ) : (
            <p className="approval-note">Le texte de l’annonce n’a pas été conservé pour ce dossier.</p>
          )}
        </>
      )}
    </details>
  )
}
