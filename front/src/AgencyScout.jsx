// Agency Scout (V3) — tableau triable qui lit /api/scout/agencies.
// Le bouton lance un scan détaché ; la page se relit seule tant que la base dit « running ».
import { useCallback, useEffect, useMemo, useState } from 'react'
import { ExternalLink, LoaderCircle, RotateCw, Search, TriangleAlert } from 'lucide-react'
import './AgencyScout.css'

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
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
