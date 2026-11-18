import { useEffect, useState } from 'react'
import { CircleCheck, Eye, RotateCw } from 'lucide-react'
import { TITLE_MAX, URL_MAX, WEBSITE_CHOICES } from './presentation'

// Panneau d'un dossier existant : site web oui/non, adresse, titre du mail,
// et aperçu du HTML exact qui partira (même rendu que l'envoi).
// Appliquer ne passe pas par l'IA : la ligne « Portfolio » est ajoutée ou
// retirée de la lettre (PDF compris) et du mail ; l'approbation tombe.
export default function DossierPresentation({ id, refreshKey = 0, onApplied, locked = false }) {
  const [form, setForm] = useState(null)
  const [state, setState] = useState({ pending: false, error: null, ok: false, warning: null })
  const [preview, setPreview] = useState({ html: '', subject: '', error: null, loading: false })
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    fetch(`/api/applications/${encodeURIComponent(id)}/presentation`, { cache: 'no-store' })
      .then(r => r.json().then(d => (r.ok ? d : Promise.reject(new Error(d.error || `HTTP ${r.status}`)))))
      .then(d => {
        if (cancelled) return
        const p = d.presentation || {}
        const current = d.attachments_current || {}
        setForm({
          show: !!p.show_website,
          websiteUrl: p.website_url || '',
          displayTitle: p.display_title || '',
          showAttachments: p.show_attachments !== false,
          cvLabel: p.cv_label || current.cv || '',
          showLetter: Boolean(p.letter_label || current.letter),
          letterLabel: p.letter_label || current.letter || 'Lettre de motivation',
        })
      })
      .catch(err => { if (!cancelled) setState(s => ({ ...s, error: err.message })) })
    return () => { cancelled = true }
  }, [id, refreshKey])

  useEffect(() => {
    let cancelled = false
    queueMicrotask(() => { if (!cancelled) setPreview(p => ({ ...p, loading: true, error: null })) })
    fetch(`/api/applications/${encodeURIComponent(id)}/mail/preview`, { cache: 'no-store' })
      .then(r => r.json().then(d => (r.ok ? d : Promise.reject(new Error(d.error || `HTTP ${r.status}`)))))
      .then(d => { if (!cancelled) setPreview({ html: d.html || '', subject: d.subject || '', error: null, loading: false }) })
      .catch(err => { if (!cancelled) setPreview({ html: '', subject: '', error: err.message, loading: false }) })
    return () => { cancelled = true }
  }, [id, refreshKey, tick])

  const apply = async () => {
    if (!form) return
    setState({ pending: true, error: null, ok: false, warning: null })
    try {
      const res = await fetch(`/api/applications/${encodeURIComponent(id)}/presentation`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          show_website: form.show,
          website_url: form.show ? form.websiteUrl : '',
          display_title: form.displayTitle,
          show_attachments: form.showAttachments,
          cv_label: form.cvLabel,
          letter_label: form.showAttachments && form.showLetter ? form.letterLabel : '',
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)
      setState({ pending: false, error: null, ok: true, warning: data.warning || null })
      setTick(t => t + 1)
      onApplied?.(data)
    } catch (err) {
      setState({ pending: false, error: err.message || 'Enregistrement impossible.', ok: false, warning: null })
    }
  }

  return (
    <section className="doc-section doc-section--info" aria-labelledby={`presentation-${id}`}>
      <div className="doc-head">
        <h2 id={`presentation-${id}`}><Eye /> Présentation et aperçu du mail</h2>
      </div>
      {form && (
        <div className="presentation-fields">
          <label className="presentation-check">
            <input
              type="checkbox"
              checked={form.show}
              disabled={locked || state.pending}
              onChange={e => setForm(f => ({ ...f, show: e.target.checked, ok: false }))}
            />
            Ajouter un site web (lettre, PDF et mail)
          </label>
          {form.show && (
            <label className="consignes-label">
              Site affiché
              <input
                type="text"
                list={`presentation-sites-${id}`}
                maxLength={URL_MAX}
                value={form.websiteUrl}
                disabled={locked || state.pending}
                onChange={e => setForm(f => ({ ...f, websiteUrl: e.target.value }))}
              />
              <datalist id={`presentation-sites-${id}`}>
                {WEBSITE_CHOICES.map(site => <option key={site} value={site} />)}
              </datalist>
            </label>
          )}
          <label className="consignes-label">
            Titre sous ton nom (signature du mail)
            <input
              type="text"
              maxLength={TITLE_MAX}
              value={form.displayTitle}
              disabled={locked || state.pending}
              onChange={e => setForm(f => ({ ...f, displayTitle: e.target.value }))}
            />
          </label>
          <fieldset className="presentation-attachments">
            <legend>Encadré « pièces jointes » du mail</legend>
            <label className="presentation-check">
              <input
                type="checkbox"
                checked={form.showAttachments}
                disabled={locked || state.pending}
                onChange={e => setForm(f => ({ ...f, showAttachments: e.target.checked }))}
              />
              Afficher l’encadré dans le mail
            </label>
            {form.showAttachments && (
              <>
                <label className="consignes-label">
                  Libellé du CV (après « CV joint : »)
                  <input
                    type="text"
                    maxLength={120}
                    value={form.cvLabel}
                    disabled={locked || state.pending}
                    placeholder="ex. CV – Facundo Varas, ou vide pour garder l’actuel"
                    onChange={e => setForm(f => ({ ...f, cvLabel: e.target.value }))}
                  />
                </label>
                <label className="presentation-check">
                  <input
                    type="checkbox"
                    checked={form.showLetter}
                    disabled={locked || state.pending}
                    onChange={e => setForm(f => ({ ...f, showLetter: e.target.checked }))}
                  />
                  Mentionner la lettre de motivation
                </label>
                {form.showLetter && (
                  <label className="consignes-label">
                    Libellé de la lettre (après « Lettre de motivation jointe : »)
                    <input
                      type="text"
                      maxLength={120}
                      value={form.letterLabel}
                      disabled={locked || state.pending}
                      onChange={e => setForm(f => ({ ...f, letterLabel: e.target.value }))}
                    />
                  </label>
                )}
              </>
            )}
            <p className="cvb-hint">
              Seul le texte du mail change. Les noms des fichiers joints se règlent dans « Noms des fichiers PDF ».
            </p>
          </fieldset>
          <div className="prepare-actions">
            <button className="prepare-btn" onClick={apply} disabled={locked || state.pending}>
              {state.pending ? 'Application…' : <><RotateCw /> Appliquer à la lettre et au mail</>}
            </button>
          </div>
        </div>
      )}
      {locked && <p className="approval-note">Une tentative d'envoi existe : la présentation est verrouillée.</p>}
      {state.ok && (
        <p className="approval-note approval-note--ok">
          <CircleCheck /> Appliqué. Relis la lettre et le mail, puis approuve à nouveau l'envoi.
        </p>
      )}
      {state.warning && <p className="approval-note approval-note--error">{state.warning}</p>}
      {state.error && <p className="approval-note approval-note--error">{state.error}</p>}

      <h3 className="presentation-preview-title">
        Aperçu du mail tel qu'il partira{preview.subject ? ` — « ${preview.subject} »` : ''}
      </h3>
      {preview.error && <p className="approval-note approval-note--error">{preview.error}</p>}
      {preview.loading && !preview.html && <p className="approval-note">Chargement de l'aperçu…</p>}
      {preview.html && (
        <iframe
          title="Aperçu du mail HTML"
          className="mail-preview-frame"
          sandbox=""
          srcDoc={preview.html}
        />
      )}
    </section>
  )
}
