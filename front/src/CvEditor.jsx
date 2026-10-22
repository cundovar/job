import { useEffect, useState } from 'react'
import { ArrowDown, ArrowUp, CircleCheck, PenLine, Plus, Trash2, TriangleAlert } from 'lucide-react'
import {
  emptyEducationForm,
  emptyExperienceForm,
  emptyProjectForm,
  emptySkillForm,
  fromForm,
  moveItem,
  removeItem,
  replaceItem,
  toForm,
} from './cvEdit'

// Éditeur du CV (demande Cundo 22/10/2026) : tu as la main sur tout le
// contenu, y compris une expérience absente du profil. Ta version est rendue
// en PDF sans IA et remplace le CV généré à l'envoi. Elle n'est pas jugée par
// le contrôle de véracité : c'est ta parole, comme un PDF que tu ajoutes.

function ListControls({ index, length, onMove, onRemove, disabled, label }) {
  return (
    <span className="cv-edit-controls">
      <button type="button" className="annuler-btn" disabled={disabled || index === 0} onClick={() => onMove(index, -1)} aria-label={`Monter ${label}`}><ArrowUp /></button>
      <button type="button" className="annuler-btn" disabled={disabled || index === length - 1} onClick={() => onMove(index, 1)} aria-label={`Descendre ${label}`}><ArrowDown /></button>
      <button type="button" className="annuler-btn" disabled={disabled} onClick={() => onRemove(index)} aria-label={`Supprimer ${label}`}><Trash2 /></button>
    </span>
  )
}

function Field({ label, value, onChange, disabled, rows, placeholder }) {
  return (
    <label className="consignes-label">
      {label}
      {rows ? (
        <textarea className="agency-consignes" rows={rows} value={value} disabled={disabled} placeholder={placeholder} onChange={e => onChange(e.target.value)} />
      ) : (
        <input type="text" value={value} disabled={disabled} placeholder={placeholder} onChange={e => onChange(e.target.value)} />
      )}
    </label>
  )
}

export default function CvEditor({ id, cvStatus, locked, onSaved }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState(null)
  const [meta, setMeta] = useState({ edited: false, warnings: [] })
  const [state, setState] = useState({ loading: false, saving: false, error: null, saved: false })
  const status = cvStatus?.status
  const hasGenerated = Boolean(cvStatus?.files?.['cv_content.json'])
  const edited = status === 'edited'

  useEffect(() => {
    if (!open || form) return
    setState(prev => ({ ...prev, loading: true, error: null }))
    fetch(`/api/applications/${id}/cv/edit`)
      .then(async res => {
        const payload = await res.json().catch(() => ({}))
        if (!res.ok) throw new Error(payload.error || `HTTP ${res.status}`)
        setForm(toForm(payload.cv, payload.online_work_effective))
        setMeta({ edited: payload.edited, warnings: payload.warnings || [] })
        setState(prev => ({ ...prev, loading: false }))
      })
      .catch(err => setState(prev => ({ ...prev, loading: false, error: err.message })))
  }, [open, form, id])

  // Une régénération ou un retrait change la base : on relira au prochain affichage.
  useEffect(() => { setForm(null) }, [id, cvStatus?.generation?.completed_at])

  if (!hasGenerated && !edited) return null

  const disabled = locked || state.saving || state.loading
  const set = patch => { setForm(prev => ({ ...prev, ...patch })); setState(prev => ({ ...prev, saved: false })) }
  const setList = (key, list) => set({ [key]: list })

  const save = async () => {
    setState(prev => ({ ...prev, saving: true, error: null, saved: false }))
    try {
      const res = await fetch(`/api/applications/${id}/cv/edit`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cv: fromForm(form) }),
      })
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload.error || `HTTP ${res.status}`)
      setMeta({ edited: true, warnings: payload.warnings || [] })
      setState(prev => ({ ...prev, saving: false, saved: true }))
      onSaved?.(id, payload)
    } catch (err) {
      setState(prev => ({ ...prev, saving: false, error: err.message || 'Enregistrement impossible.' }))
    }
  }

  const reset = async () => {
    if (!window.confirm('Retirer ta version ? Le CV généré redeviendra celui qui part (s’il est validé).')) return
    setState(prev => ({ ...prev, saving: true, error: null, saved: false }))
    try {
      const res = await fetch(`/api/applications/${id}/cv/edit`, { method: 'DELETE' })
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload.error || `HTTP ${res.status}`)
      setForm(null)
      setMeta({ edited: false, warnings: [] })
      setState(prev => ({ ...prev, saving: false }))
      onSaved?.(id, payload)
    } catch (err) {
      setState(prev => ({ ...prev, saving: false, error: err.message || 'Retrait impossible.' }))
    }
  }

  return (
    <details className="consignes-details cv-editor" open={open || undefined} onToggle={e => setOpen(e.currentTarget.open)}>
      <summary>
        <PenLine /> Modifier le CV {edited ? <span className="consignes-optional">(ta version part)</span> : <span className="consignes-optional">(optionnel)</span>}
      </summary>
      <div className="consignes-editor">
        <p className="approval-note">
          Tout est modifiable, y compris une expérience absente de ton profil. Ta version est mise en page sans IA
          et remplace le CV généré à l’envoi. Régénérer le CV met ta version de côté.
          {edited && <> <a href={`/api/applications/${id}/cv/download/cv_edit.pdf`}>Voir ta version (PDF)</a></>}
        </p>
        {state.loading && <p className="approval-note">Chargement…</p>}
        {form && (
          <>
            <Field label="Titre du CV" value={form.title} disabled={disabled} onChange={title => set({ title })} />
            <Field label="Accroche" rows={3} value={form.profile} disabled={disabled} onChange={profile => set({ profile })} />

            <h4>Coordonnées</h4>
            <Field label="Email" value={form.contact.email} disabled={disabled} onChange={email => set({ contact: { ...form.contact, email } })} />
            <Field label="Téléphone" value={form.contact.phone} disabled={disabled} onChange={phone => set({ contact: { ...form.contact, phone } })} />
            <Field label="Ville / zone" value={form.location} disabled={disabled} onChange={location => set({ location })} />
            <Field label="Site / portfolio (https://…, vide = aucun)" value={form.contact.portfolio} disabled={disabled} onChange={portfolio => set({ contact: { ...form.contact, portfolio } })} />
            <Field label="GitHub (https://…, vide = aucun)" value={form.contact.github} disabled={disabled} onChange={github => set({ contact: { ...form.contact, github } })} />
            <Field label="LinkedIn (https://…, vide = aucun)" value={form.contact.linkedin} disabled={disabled} onChange={linkedin => set({ contact: { ...form.contact, linkedin } })} />

            <h4>Expériences</h4>
            {form.experiences.map((exp, index) => (
              <fieldset key={index} className="cv-edit-item">
                <legend>
                  {exp.title || exp.organization || `Expérience ${index + 1}`}
                  <ListControls index={index} length={form.experiences.length} disabled={disabled} label="l’expérience"
                    onMove={(i, d) => setList('experiences', moveItem(form.experiences, i, d))}
                    onRemove={i => setList('experiences', removeItem(form.experiences, i))} />
                </legend>
                <Field label="Intitulé" value={exp.title} disabled={disabled} onChange={title => setList('experiences', replaceItem(form.experiences, index, { title }))} />
                <Field label="Structure" value={exp.organization} disabled={disabled} onChange={organization => setList('experiences', replaceItem(form.experiences, index, { organization }))} />
                <Field label="Période" value={exp.period} disabled={disabled} placeholder="2026-01 – Aujourd’hui" onChange={period => setList('experiences', replaceItem(form.experiences, index, { period }))} />
                <Field label="Puces (une par ligne)" rows={4} value={exp.bulletsText} disabled={disabled} onChange={bulletsText => setList('experiences', replaceItem(form.experiences, index, { bulletsText }))} />
                <Field label="Liens (un par ligne)" rows={2} value={exp.linksText} disabled={disabled} onChange={linksText => setList('experiences', replaceItem(form.experiences, index, { linksText }))} />
              </fieldset>
            ))}
            <button type="button" className="copy-btn" disabled={disabled} onClick={() => setList('experiences', [...form.experiences, emptyExperienceForm()])}><Plus /> Ajouter une expérience</button>

            <h4>Projets personnels</h4>
            {form.projects.map((project, index) => (
              <fieldset key={index} className="cv-edit-item">
                <legend>
                  {project.title || `Projet ${index + 1}`}
                  <ListControls index={index} length={form.projects.length} disabled={disabled} label="le projet"
                    onMove={(i, d) => setList('projects', moveItem(form.projects, i, d))}
                    onRemove={i => setList('projects', removeItem(form.projects, i))} />
                </legend>
                <Field label="Titre" value={project.title} disabled={disabled} onChange={title => setList('projects', replaceItem(form.projects, index, { title }))} />
                <Field label="Description" rows={3} value={project.description} disabled={disabled} onChange={description => setList('projects', replaceItem(form.projects, index, { description }))} />
                <Field label="Technologies (séparées par des virgules, vide = aucune)" value={project.technologiesText} disabled={disabled} onChange={technologiesText => setList('projects', replaceItem(form.projects, index, { technologiesText }))} />
                <Field label="Liens (un par ligne)" rows={2} value={project.linksText} disabled={disabled} onChange={linksText => setList('projects', replaceItem(form.projects, index, { linksText }))} />
              </fieldset>
            ))}
            <button type="button" className="copy-btn" disabled={disabled} onClick={() => setList('projects', [...form.projects, emptyProjectForm()])}><Plus /> Ajouter un projet</button>

            <h4>Compétences</h4>
            {form.skills.map((group, index) => (
              <fieldset key={index} className="cv-edit-item">
                <legend>
                  {group.title || `Groupe ${index + 1}`}
                  <ListControls index={index} length={form.skills.length} disabled={disabled} label="le groupe"
                    onMove={(i, d) => setList('skills', moveItem(form.skills, i, d))}
                    onRemove={i => setList('skills', removeItem(form.skills, i))} />
                </legend>
                <Field label="Titre du groupe" value={group.title} disabled={disabled} onChange={title => setList('skills', replaceItem(form.skills, index, { title }))} />
                <Field label="Compétences (séparées par des virgules)" value={group.itemsText} disabled={disabled} onChange={itemsText => setList('skills', replaceItem(form.skills, index, { itemsText }))} />
              </fieldset>
            ))}
            <button type="button" className="copy-btn" disabled={disabled} onClick={() => setList('skills', [...form.skills, emptySkillForm()])}><Plus /> Ajouter un groupe</button>

            <h4>Formation</h4>
            {form.education.map((edu, index) => (
              <fieldset key={index} className="cv-edit-item">
                <legend>
                  {edu.title || `Diplôme ${index + 1}`}
                  <ListControls index={index} length={form.education.length} disabled={disabled} label="le diplôme"
                    onMove={(i, d) => setList('education', moveItem(form.education, i, d))}
                    onRemove={i => setList('education', removeItem(form.education, i))} />
                </legend>
                <Field label="Année" value={edu.year} disabled={disabled} onChange={year => setList('education', replaceItem(form.education, index, { year }))} />
                <Field label="Intitulé" value={edu.title} disabled={disabled} onChange={title => setList('education', replaceItem(form.education, index, { title }))} />
                <Field label="Niveau" value={edu.level} disabled={disabled} onChange={level => setList('education', replaceItem(form.education, index, { level }))} />
                <Field label="Établissement" value={edu.school} disabled={disabled} onChange={school => setList('education', replaceItem(form.education, index, { school }))} />
                <Field label="Statut (vide = rien d’affiché)" value={edu.status} disabled={disabled} onChange={status => setList('education', replaceItem(form.education, index, { status }))} />
              </fieldset>
            ))}
            <button type="button" className="copy-btn" disabled={disabled} onClick={() => setList('education', [...form.education, emptyEducationForm()])}><Plus /> Ajouter un diplôme</button>

            <h4>Réalisations en ligne</h4>
            <Field label="Une par ligne : libellé | https://… (vide = rubrique masquée)" rows={3} value={form.onlineWorkText} disabled={disabled}
              placeholder="mediateur.varascundo.com | https://mediateur.varascundo.com/"
              onChange={onlineWorkText => set({ onlineWorkText, onlineWorkCustom: true })} />
            <p className="approval-note">
              {form.onlineWorkCustom
                ? 'Liste choisie par toi : c’est elle qui s’affiche.'
                : 'Liste calculée automatiquement à partir de tes expériences et projets. Modifie-la pour la fixer.'}
            </p>

            <h4>Langues</h4>
            <Field label="Une par ligne : langue | niveau" rows={2} value={form.languagesText} disabled={disabled}
              placeholder="Français | courant"
              onChange={languagesText => set({ languagesText })} />

            <div className="cv-edit-actions">
              <button type="button" className="copy-btn" disabled={disabled} onClick={save}>
                {state.saving ? 'Enregistrement…' : 'Enregistrer ma version'}
              </button>
              {(meta.edited || edited) && (
                <button type="button" className="annuler-btn" disabled={disabled} onClick={reset}>Revenir au CV généré</button>
              )}
            </div>
          </>
        )}
        {locked && <p className="approval-note">Une tentative d’envoi existe : le CV est verrouillé.</p>}
        {state.saved && <p className="approval-note" style={{ color: '#0F6E66' }}><CircleCheck /> Ta version est enregistrée : c’est elle qui part. L’approbation d’envoi est retirée.</p>}
        {meta.warnings.length > 0 && (
          <ul className="approval-note cv-edit-warnings">
            {meta.warnings.map(warning => <li key={warning}><TriangleAlert /> {warning}</li>)}
          </ul>
        )}
        {state.error && <p className="approval-note" style={{ color: '#fb7185' }}>{state.error}</p>}
      </div>
    </details>
  )
}
