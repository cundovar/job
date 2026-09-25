/**
 * Tri des agences : « retenu », « écarté », ou rien encore.
 *
 * Trois états et non deux : avec un simple bascule, tout serait « non retenu »
 * au départ et le rouge ne dirait plus rien. Seules les deux décisions
 * explicites sont des décisions ; l'absence en est l'absence.
 *
 * La décision porte sur le **domaine**, pas sur la ligne d'une recherche : la
 * même agence ressortie d'un autre scan reste celle qu'on a déjà jugée.
 */
import { useCallback, useEffect, useState } from 'react'

export const A_DECIDER = 'a-decider'

/**
 * Même forme de domaine que le serveur. Sans ça, la carte V2 (qui lit
 * `www.exemple.fr` dans l'URL) et le scout (qui stocke `exemple.fr`)
 * désigneraient deux agences là où il n'y en a qu'une.
 */
export function domainKey(value) {
  if (!value || typeof value !== 'string') return ''
  return value.toLowerCase().trim()
    .replace(/^https?:\/\//, '')
    .replace(/^www\./, '')
    .split('/')[0]
    .split('?')[0]
}

/** Compte les trois états dans une liste, pour des filtres qui disent vrai. */
export function decisionCounts(items, read) {
  const counts = { retenu: 0, ecarte: 0, [A_DECIDER]: 0, toutes: 0 }
  for (const item of items || []) {
    const value = read(item)
    counts[value === 'retenu' || value === 'ecarte' ? value : A_DECIDER] += 1
    counts.toutes += 1
  }
  return counts
}

/** `filtre` vide = tout passe : on ne cache rien sans que ce soit demandé. */
export function matchesDecision(value, filtre) {
  if (!filtre) return true
  if (filtre === A_DECIDER) return value !== 'retenu' && value !== 'ecarte'
  return value === filtre
}

export function useAgencyDecisions() {
  const [decisions, setDecisions] = useState({})
  const [pending, setPending] = useState({})
  const [error, setError] = useState('')

  const load = useCallback(() => {
    fetch('/api/agencies/decisions')
      .then(r => (r.ok ? r.json() : null))
      .then(data => setDecisions(data?.decisions || {}))
      .catch(() => { /* pas de décision lisible : la liste s'affiche sans tri */ })
  }, [])

  useEffect(() => { load() }, [load])

  const decisionOf = useCallback(
    domain => decisions[domainKey(domain)]?.decision || '',
    [decisions],
  )

  /** Recliquer sur l'état actif l'enlève : une décision se reprend. */
  const decide = useCallback(async (brut, valeur, source = '') => {
    const domain = domainKey(brut)
    if (!domain) return
    const actuel = decisions[domain]?.decision || ''
    const cible = actuel === valeur ? null : valeur
    setPending(prev => ({ ...prev, [domain]: true }))
    setError('')
    try {
      const res = await fetch(`/api/agencies/decisions/${encodeURIComponent(domain)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision: cible, source }),
      })
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload.error || `HTTP ${res.status}`)
      setDecisions(prev => {
        const copie = { ...prev }
        if (cible === null) delete copie[domain]
        else copie[domain] = { domain, decision: cible, decided_at: payload.decided_at || null, source }
        return copie
      })
    } catch (err) {
      setError(err.message || 'Décision non enregistrée.')
    } finally {
      setPending(prev => ({ ...prev, [domain]: false }))
    }
  }, [decisions])

  // Les appelants passent le domaine tel qu'ils l'ont : la normalisation est
  // ici, une seule fois, sinon une page attend sur une clé que l'autre n'écrit pas.
  const pendingOf = useCallback(domain => Boolean(pending[domainKey(domain)]), [pending])

  return { decisions, decisionOf, decide, pendingOf, error, reload: load }
}
