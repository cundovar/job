// Agency Scout (V3) — tableau triable qui lit /api/scout/agencies.
// Le bouton lance un scan détaché ; la page se relit seule tant que la base dit « running ».
import { useCallback, useEffect, useMemo, useState } from 'react'
import { ExternalLink, LoaderCircle, RotateCw, Search, TriangleAlert } from 'lucide-react'
import './AgencyScout.css'

const SCOUT_TARGET_TASKS_KEY = 'scout_target_tasks'

const COLUMNS = [
  { key: 'name', label: 'Structure' },
  { key: 'categorie', label: 'Catégorie' },
  { key: 'score', label: 'Score' },
  { key: 'distance_m', label: 'Distance' },
]

function fmtDistance(m) {
  if (m == null) return '—'
  return m < 1000 ? `${m} m` : `${(m / 1000).toFixed(1).replace('.', ',')} km`
}

function compare(a, b, key) {
  const x = a[key], y = b[key]
  if (x == null && y == null) return 0
  if (x == null) return 1
  if (y == null) return -1
  return typeof x === 'number' ? x - y : String(x).localeCompare(String(y), 'fr')
}

export default function AgencyScout() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [sort, setSort] = useState({ key: 'score', dir: -1 })
  const [categorie, setCategorie] = useState('')
  const [rayon, setRayon] = useState(3000)
  const [cp, setCp] = useState('')
  const [launching, setLaunching] = useState(false)
  // Ciblage par domaine : { pending, done, error, taskId }. Le task_id vit dans
  // le localStorage : changer de page pendant une préparation ne perd rien.
  const [targeting, setTargeting] = useState({})

  const setTargetState = (domain, patch) =>
    setTargeting((s) => ({ ...s, [domain]: { ...(s[domain] || {}), ...patch } }))

  const load = useCallback(async () => {
    try {
      const r = await fetch('/api/scout/agencies')
      const json = await r.json()
      if (!r.ok) throw new Error(json.error || `HTTP ${r.status}`)
      setData(json)
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }, [])

  useEffect(() => {
    const t = setTimeout(load, 0)
    return () => clearTimeout(t)
  }, [load])

  // Relecture de la base pendant un scan uniquement (pas de file de tâches côté serveur).
  useEffect(() => {
    if (!data?.running) return undefined
    const t = setInterval(load, 10000)
    return () => clearInterval(t)
  }, [data?.running, load])

  // Reprise des ciblages en cours au remontage de la vue : le task_id persisté
  // dans le localStorage est réinterrogé ; 404 = serveur redémarré, on nettoie
  // honnêtement au lieu de faire croire que ça tourne encore.
  useEffect(() => {
    const readTasks = () => {
      try { return JSON.parse(localStorage.getItem(SCOUT_TARGET_TASKS_KEY) || '{}') } catch { return {} }
    }
    const saveTasks = (tasks) => localStorage.setItem(SCOUT_TARGET_TASKS_KEY, JSON.stringify(tasks))
    let tasks = readTasks()
    const pending = Object.entries(tasks).filter(([, t]) => t?.task_id && !t.done && !t.error)
    if (pending.length === 0) return undefined
    let cancelled = false
    const watch = (domain, taskId) => {
      const tick = async () => {
        try {
          const r = await fetch(`/api/agencies/target/status/${encodeURIComponent(taskId)}`)
          if (cancelled) return
          if (r.status === 404) {
            setTargetState(domain, { pending: false, error: 'Tâche introuvable (serveur redémarré) — vérifie l’onglet Candidatures.' })
            delete tasks[domain]
            saveTasks(tasks)
            return
          }
          const json = await r.json()
          if (cancelled) return
          if (json.state === 'completed' || json.state === 'failed') {
            const done = json.state === 'completed'
            setTargetState(domain, { pending: false, done, error: done ? null : (json.error || 'Échec de la préparation') })
            tasks[domain] = { task_id: taskId, done, error: done ? null : (json.error || '') }
            saveTasks(tasks)
          } else {
            setTimeout(tick, 4000)
          }
        } catch {
          if (!cancelled) setTimeout(tick, 6000)
        }
      }
      tick()
    }
    pending.forEach(([domain, t]) => {
      setTargetState(domain, { pending: true, taskId: t.task_id })
      watch(domain, t.task_id)
    })
    return () => { cancelled = true }
  }, [])

  const launch = async () => {
    setLaunching(true)
    try {
      const r = await fetch('/api/scout/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // CP rempli = mode arrondissement : le code postal décide, le rayon ne filtre plus.
        body: JSON.stringify({ rayon: Number(rayon), ...(cp.trim() ? { cp: cp.trim() } : {}) }),
      })
      const json = await r.json()
      if (!r.ok) throw new Error(json.error || `HTTP ${r.status}`)
      setTimeout(load, 1500)
    } catch (e) {
      setError(e.message)
    } finally {
      setLaunching(false)
    }
  }

  const rows = useMemo(() => {
    const list = (data?.agencies || []).filter((a) => !categorie || a.categorie === categorie)
    return [...list].sort((a, b) => sort.dir * compare(a, b, sort.key))
  }, [data, categorie, sort])

  // Retenir & préparer : même circuit que la V2 (POST /api/agencies/target,
  // source=scout). Le serveur vérifie le domaine dans la base scout, ajoute
  // la ligne au banc d'essai (statut retenue) et rend un task_id pollable.
  const target = async (a) => {
    const domain = a.domain
    if (!domain || targeting[domain]?.pending) return
    setTargetState(domain, { pending: true, done: false, error: null })
    try {
      const r = await fetch('/api/agencies/target', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: 'scout', domain }),
      })
      const json = await r.json()
      if (!r.ok) throw new Error(json.error || `HTTP ${r.status}`)
      const tasks = (() => { try { return JSON.parse(localStorage.getItem(SCOUT_TARGET_TASKS_KEY) || '{}') } catch { return {} } })()
      tasks[domain] = { task_id: json.task_id }
      localStorage.setItem(SCOUT_TARGET_TASKS_KEY, JSON.stringify(tasks))
      setTargetState(domain, { taskId: json.task_id })
      const tick = async () => {
        const sr = await fetch(`/api/agencies/target/status/${encodeURIComponent(json.task_id)}`)
        if (sr.status === 404) {
          setTargetState(domain, { pending: false, error: 'Tâche introuvable (serveur redémarré) — vérifie l’onglet Candidatures.' })
          return
        }
        const sj = await sr.json()
        if (sj.state === 'completed' || sj.state === 'failed') {
          const done = sj.state === 'completed'
          setTargetState(domain, { pending: false, done, error: done ? null : (sj.error || 'Échec de la préparation') })
          const t2 = (() => { try { return JSON.parse(localStorage.getItem(SCOUT_TARGET_TASKS_KEY) || '{}') } catch { return {} } })()
          t2[domain] = { task_id: json.task_id, done, error: done ? null : (sj.error || '') }
          localStorage.setItem(SCOUT_TARGET_TASKS_KEY, JSON.stringify(t2))
        } else {
          setTimeout(tick, 4000)
        }
      }
      tick()
    } catch (e) {
      setTargetState(domain, { pending: false, error: e.message })
    }
  }

  const toggleSort = (key) =>
    setSort((s) => (s.key === key ? { key, dir: -s.dir } : { key, dir: key === 'score' ? -1 : 1 }))

  return (
    <section className="scout">
      <header className="scout-header">
        <div>
          <h1>Agences — Google Places + IA</h1>
          <p className="scout-meta">
            {data?.last_scan
              ? `Dernier scan : ${new Date(data.last_scan.finished_at).toLocaleString('fr-FR')} · ${data.last_scan.places} lieux · ${data.last_scan.postal_codes?.length ? `CP ${data.last_scan.postal_codes.join(', ')}` : `rayon ${fmtDistance(data.last_scan.radius_m)}`}`
              : 'Aucun scan pour l’instant.'}
            {data && ` · Quota Places : ${data.places_calls_this_month}/${data.places_monthly_cap} ce mois`}
          </p>
        </div>
        <div className="scout-actions">
          <label>
            Code postal
            <input
              className="scout-cp"
              type="text"
              value={cp}
              onChange={(e) => setCp(e.target.value)}
              placeholder="ex. 75020"
              inputMode="numeric"
            />
          </label>
          <label>
            Rayon
            <select value={rayon} onChange={(e) => setRayon(e.target.value)}>
              {[1000, 2000, 3000, 5000, 10000].map((r) => <option key={r} value={r}>{fmtDistance(r)}</option>)}
            </select>
          </label>
          <button type="button" className="btn-primary" onClick={launch} disabled={launching || !!data?.running}>
            {data?.running ? <LoaderCircle size={16} className="spin" /> : <Search size={16} />}
            {data?.running ? 'Scan en cours…' : 'Lancer un scan'}
          </button>
          <button type="button" className="btn-secondary" onClick={load} title="Relire la base">
            <RotateCw size={16} />
          </button>
        </div>
      </header>

      {error && <p className="scout-error"><TriangleAlert size={16} /> {error}</p>}

      <div className="scout-filters">
        {[['', 'Toutes'], ['agence', 'Agences'], ['formation', 'Formation'], ['autre', 'Autres']].map(([v, l]) => (
          <button key={v} type="button" className={categorie === v ? 'chip active' : 'chip'} onClick={() => setCategorie(v)}>{l}</button>
        ))}
        <span className="scout-count">{rows.length} structures</span>
      </div>

      <div className="scout-table-wrap">
        <table className="scout-table">
          <thead>
            <tr>
              {COLUMNS.map((c) => (
                <th key={c.key} onClick={() => toggleSort(c.key)} aria-sort={sort.key === c.key ? (sort.dir > 0 ? 'ascending' : 'descending') : 'none'}>
                  {c.label}{sort.key === c.key ? (sort.dir > 0 ? ' ▲' : ' ▼') : ''}
                </th>
              ))}
              <th>Analyse</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.place_id}>
                <td>
                  <strong>{a.name}</strong>
                  <div className="scout-sub">{a.address}</div>
                  {a.website && (
                    <a href={a.website} target="_blank" rel="noreferrer" className="scout-link">
                      {a.domain} <ExternalLink size={12} />
                    </a>
                  )}
                  {a.emails && a.emails.length > 0 && (
                    <div className="scout-emails">
                      {a.emails.slice(0, 3).map((e) => (
                        <a key={e} href={`mailto:${e}`}>✉ {e}</a>
                      ))}
                    </div>
                  )}
                </td>
                <td>{a.categorie ? <span className={`badge badge-${a.categorie}`}>{a.categorie}</span> : '—'}</td>
                <td className="scout-score">{a.score ?? '—'}{a.score != null && <small>/10</small>}</td>
                <td>{fmtDistance(a.distance_m)}</td>
                <td className="scout-analysis">
                  {a.resume && <p>{a.resume}</p>}
                  {a.preuve && (
                    <blockquote className={a.preuve_ok ? '' : 'unverified'}>
                      « {a.preuve} »{!a.preuve_ok && <em> — citation non retrouvée sur le site</em>}
                    </blockquote>
                  )}
                  {!a.resume && <span className="scout-sub">{a.error || (a.website ? 'Pas encore analysé' : 'Pas de site web sur Google')}</span>}
                </td>
                <td className="scout-action">
                  {a.domain && (
                    <button
                      type="button"
                      className="btn-scout-target"
                      onClick={() => target(a)}
                      disabled={targeting[a.domain]?.pending}
                    >
                      {targeting[a.domain]?.pending
                        ? '⏳ Préparation…'
                        : targeting[a.domain]?.done
                          ? '✓ Ciblé'
                          : '🎯 Retenir & préparer'}
                    </button>
                  )}
                  {targeting[a.domain]?.error && (
                    <div className="scout-target-error">{targeting[a.domain].error}</div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
