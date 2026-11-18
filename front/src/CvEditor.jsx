import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  closestCenter,
  pointerWithin,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { CircleCheck, FileDown, GripVertical, PenLine, Plus, Trash2, TriangleAlert } from 'lucide-react'
import {
  CATALOG_SECTIONS,
  ITEM_FACTORIES,
  SECTION_LABELS,
  availableFromCatalog,
  catalogEntryToItem,
  emptyBullet,
  fromBoard,
  moveByKey,
  toBoard,
} from './cvBoard'

// Éditeur du CV, version visuelle (demande Cundo 18/11/2026) : la page
// ressemble au CV (colonne teintée à gauche, colonne principale à droite),
// chaque texte se modifie là où il s'affiche, et rubriques, blocs et puces se
// réordonnent par glisser-déposer (poignée ⋮⋮, souris, doigt ou clavier).
//
// Règles inchangées depuis le 22/10/2026 : tout est modifiable, y compris une
// expérience absente du profil. Ta version est rendue en PDF sans IA et
// remplace le CV généré à l'envoi ; elle n'est pas jugée par le contrôle de
// véracité, c'est ta parole.

// Les rubriques sont hautes : on suit le pointeur plutôt que le centre du
// bloc déplacé, sinon il faudrait le traîner bien au-delà de sa cible. Les
// blocs et puces, de tailles proches, restent sur closestCenter.
function pointerFirst(args) {
  const hits = pointerWithin(args)
  return hits.length ? hits : closestCenter(args)
}

function useDndSensors() {
  return useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 180, tolerance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )
}

// Liste réordonnable : un contexte par liste, pour qu'une puce ne puisse
// jamais tomber dans une autre rubrique.
function SortableList({ items, onReorder, children, disabled }) {
  const sensors = useDndSensors()
  const keys = items.map(item => item._key)
  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragEnd={({ active, over }) => {
        if (!disabled && over && active.id !== over.id) onReorder(moveByKey(items, active.id, over.id))
      }}
    >
      <SortableContext items={keys} strategy={verticalListSortingStrategy} disabled={disabled}>
        {children}
      </SortableContext>
    </DndContext>
  )
}

function SortableBlock({ id, className = '', handleLabel, onRemove, removeLabel, disabled, children }) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({ id, disabled })
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`cvb-block ${className} ${isDragging ? 'is-dragging' : ''}`}
    >
      <button
        type="button"
        ref={setActivatorNodeRef}
        className="cvb-handle"
        aria-label={handleLabel}
        title="Glisser pour déplacer"
        disabled={disabled}
        {...attributes}
        {...listeners}
      >
        <GripVertical />
      </button>
      <div className="cvb-block-body">{children}</div>
      {onRemove && (
        <button type="button" className="cvb-remove" aria-label={removeLabel} title={removeLabel} disabled={disabled} onClick={onRemove}>
          <Trash2 />
        </button>
      )}
    </div>
  )
}

// Texte modifiable sur place : sans cadre, il se lit comme le CV ; le cadre
// n'apparaît qu'au survol et au focus.
function fitHeight(el) {
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${el.scrollHeight}px`
}

function Inline({ value, onChange, placeholder, className = '', disabled, multiline = false, onKeyDown, inputRef, label }) {
  const ref = useRef(null)
  useLayoutEffect(() => {
    if (!multiline) return undefined
    const el = ref.current
    fitHeight(el)
    // La largeur change (panneau ouvert, fenêtre redimensionnée, police
    // chargée) : la hauteur suit.
    if (!el || typeof ResizeObserver === 'undefined') return undefined
    let width = el.clientWidth
    const observer = new ResizeObserver(() => {
      if (el.clientWidth !== width) { width = el.clientWidth; fitHeight(el) }
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [value, multiline])
  const common = {
    ref: el => {
      ref.current = el
      if (typeof inputRef === 'function') inputRef(el)
    },
    className: `cvb-inline ${className}`,
    value,
    placeholder,
    disabled,
    'aria-label': label || placeholder,
    onChange: e => onChange(e.target.value),
    onKeyDown,
  }
  return multiline ? <textarea rows={1} {...common} /> : <input type="text" {...common} />
}

function Bullets({ bullets, onChange, disabled }) {
  const refs = useRef({})
  const [focusKey, setFocusKey] = useState(null)
  useEffect(() => {
    if (focusKey && refs.current[focusKey]) {
      refs.current[focusKey].focus()
      setFocusKey(null)
    }
  }, [focusKey, bullets])

  const update = (key, text) => onChange(bullets.map(b => (b._key === key ? { ...b, text } : b)))
  const insertAfter = key => {
    const index = bullets.findIndex(b => b._key === key)
    const bullet = emptyBullet()
    onChange([...bullets.slice(0, index + 1), bullet, ...bullets.slice(index + 1)])
    setFocusKey(bullet._key)
  }
  const remove = key => {
    const index = bullets.findIndex(b => b._key === key)
    const next = bullets.filter(b => b._key !== key)
    onChange(next)
    const previous = next[Math.max(0, index - 1)]
    if (previous) setFocusKey(previous._key)
  }

  return (
    <div className="cvb-bullets">
      <SortableList items={bullets} onReorder={onChange} disabled={disabled}>
        {bullets.map(bullet => (
          <SortableBlock key={bullet._key} id={bullet._key} className="cvb-bullet" disabled={disabled}
            handleLabel="Déplacer la puce" onRemove={() => remove(bullet._key)} removeLabel="Supprimer la puce">
            <span className="cvb-dot" aria-hidden="true">•</span>
            <Inline
              multiline
              value={bullet.text}
              disabled={disabled}
              placeholder="Une réalisation, une mission…"
              label="Puce"
              inputRef={el => { refs.current[bullet._key] = el }}
              onChange={text => update(bullet._key, text)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); insertAfter(bullet._key) }
                if (e.key === 'Backspace' && !bullet.text) { e.preventDefault(); remove(bullet._key) }
              }}
            />
          </SortableBlock>
        ))}
      </SortableList>
      <button type="button" className="cvb-add cvb-add--small" disabled={disabled}
        onClick={() => onChange([...bullets, emptyBullet()])}>
        <Plus /> Puce
      </button>
    </div>
  )
}

function ExperienceBlock({ item, patch, disabled }) {
  return (
    <>
      <Inline className="cvb-item-title" value={item.title} disabled={disabled} placeholder="Intitulé du poste" onChange={title => patch({ title })} />
      <div className="cvb-item-meta">
        <Inline value={item.organization} disabled={disabled} placeholder="Structure" onChange={organization => patch({ organization })} />
        <span aria-hidden="true">·</span>
        <Inline className="cvb-period" value={item.period} disabled={disabled} placeholder="2026-01 – Aujourd’hui" label="Période" onChange={period => patch({ period })} />
      </div>
      <Bullets bullets={item.bullets} disabled={disabled} onChange={bullets => patch({ bullets })} />
      <Inline className="cvb-links" multiline value={item.linksText} disabled={disabled} placeholder="Liens (un par ligne, facultatif)" label="Liens" onChange={linksText => patch({ linksText })} />
    </>
  )
}

function ProjectBlock({ item, patch, disabled }) {
  return (
    <>
      <Inline className="cvb-item-title" value={item.title} disabled={disabled} placeholder="Titre du projet" onChange={title => patch({ title })} />
      <Inline multiline value={item.description} disabled={disabled} placeholder="Description" onChange={description => patch({ description })} />
      <Inline className="cvb-tech" value={item.technologiesText} disabled={disabled} placeholder="Technologies, séparées par des virgules" label="Technologies" onChange={technologiesText => patch({ technologiesText })} />
      <Inline className="cvb-links" multiline value={item.linksText} disabled={disabled} placeholder="Liens (un par ligne, facultatif)" label="Liens" onChange={linksText => patch({ linksText })} />
    </>
  )
}

function SkillBlock({ item, patch, disabled }) {
  return (
    <>
      <Inline className="cvb-skill-title" value={item.title} disabled={disabled} placeholder="Groupe de compétences" onChange={title => patch({ title })} />
      <Inline multiline value={item.itemsText} disabled={disabled} placeholder="Compétences, séparées par des virgules" label="Compétences" onChange={itemsText => patch({ itemsText })} />
    </>
  )
}

function EducationBlock({ item, patch, disabled }) {
  return (
    <>
      <div className="cvb-edu-line">
        <Inline className="cvb-year" value={item.year} disabled={disabled} placeholder="Année" onChange={year => patch({ year })} />
        <Inline className="cvb-item-title" value={item.title} disabled={disabled} placeholder="Intitulé du diplôme" onChange={title => patch({ title })} />
      </div>
      <div className="cvb-item-meta">
        <Inline value={item.level} disabled={disabled} placeholder="Niveau" onChange={level => patch({ level })} />
        <span aria-hidden="true">·</span>
        <Inline value={item.school} disabled={disabled} placeholder="Établissement" onChange={school => patch({ school })} />
      </div>
      <Inline className="cvb-status" value={item.status} disabled={disabled} placeholder="Statut (ex. VAE en cours) — vide = rien" label="Statut" onChange={status => patch({ status })} />
    </>
  )
}

const BLOCKS = {
  experiences: { Component: ExperienceBlock, noun: 'l’expérience', add: 'Expérience' },
  projects: { Component: ProjectBlock, noun: 'le projet', add: 'Projet' },
  skills: { Component: SkillBlock, noun: 'le groupe', add: 'Groupe' },
  education: { Component: EducationBlock, noun: 'le diplôme', add: 'Diplôme' },
}

// Ce que ton profil contient et que la page n'affiche pas : un clic l'ajoute
// en bas de la rubrique, où il se modifie et se déplace comme le reste.
function CatalogPicker({ name, catalog, board, onAdd, disabled }) {
  const available = availableFromCatalog(catalog, board, name)
  if (!CATALOG_SECTIONS.includes(name) || available.length === 0) return null
  return (
    <details className="cvb-catalog">
      <summary>
        <Plus /> Ajouter depuis ton profil <span className="cvb-catalog-count">{available.length}</span>
      </summary>
      <ul>
        {available.map(entry => (
          <li key={entry.id || entry.title}>
            <button type="button" className="cvb-catalog-item" disabled={disabled} onClick={() => onAdd(entry)}
              title="Ajouter au CV">
              <span className="cvb-catalog-title">{entry.title || entry.organization}</span>
              <span className="cvb-catalog-meta">
                {name === 'experiences' && [entry.organization, entry.period].filter(Boolean).join(' · ')}
                {name === 'projects' && [entry.year, (entry.technologies || []).slice(0, 4).join(', ')].filter(Boolean).join(' · ')}
                {name === 'education' && [entry.year, entry.level, entry.school, entry.status].filter(Boolean).join(' · ')}
              </span>
              {name === 'experiences' && entry.bullets?.[0] && <span className="cvb-catalog-preview">{entry.bullets[0]}</span>}
              {name === 'projects' && entry.description && <span className="cvb-catalog-preview">{entry.description}</span>}
              <Plus className="cvb-catalog-plus" />
            </button>
          </li>
        ))}
      </ul>
    </details>
  )
}

function MainSection({ name, board, setList, disabled, catalog }) {
  const items = board[name]
  const { Component, noun, add } = BLOCKS[name]
  const isEmpty = items.length === 0
  return (
    <>
      <div className="cvb-section-head">
        <h3 className="cvb-section-title">{SECTION_LABELS[name]}</h3>
        <button type="button" className="cvb-add" disabled={disabled} onClick={() => setList(name, [...items, ITEM_FACTORIES[name]()])}>
          <Plus /> {add}
        </button>
      </div>
      <CatalogPicker name={name} catalog={catalog} board={board} disabled={disabled}
        onAdd={entry => setList(name, [...items, catalogEntryToItem(name, entry)])} />
      {isEmpty && <p className="cvb-empty">Rubrique vide : elle n’apparaîtra pas sur le CV.</p>}
      <SortableList items={items} onReorder={list => setList(name, list)} disabled={disabled}>
        {items.map((item, index) => (
          <SortableBlock key={item._key} id={item._key} className="cvb-item" disabled={disabled}
            handleLabel={`Déplacer ${noun}`} removeLabel={`Supprimer ${noun}`}
            onRemove={() => setList(name, items.filter((_, i) => i !== index))}>
            <Component item={item} disabled={disabled}
              patch={p => setList(name, items.map((it, i) => (i === index ? { ...it, ...p } : it)))} />
          </SortableBlock>
        ))}
      </SortableList>
    </>
  )
}

function SideField({ title, children }) {
  return (
    <div className="cvb-side-block">
      <h3 className="cvb-side-title">{title}</h3>
      {children}
    </div>
  )
}

export default function CvEditor({ id, cvStatus, locked, onSaved }) {
  const [open, setOpen] = useState(false)
  const [board, setBoard] = useState(null)
  const [catalog, setCatalog] = useState(null)
  const [meta, setMeta] = useState({ edited: false, warnings: [] })
  const [state, setState] = useState({ loading: false, saving: false, error: null, saved: false, dirty: false })
  const sensors = useDndSensors()
  const status = cvStatus?.status
  const hasGenerated = Boolean(cvStatus?.files?.['cv_content.json'])
  const edited = status === 'edited'

  useEffect(() => {
    if (!open || board) return
    queueMicrotask(() => setState(prev => ({ ...prev, loading: true, error: null })))
    fetch(`/api/applications/${id}/cv/edit`)
      .then(async res => {
        const payload = await res.json().catch(() => ({}))
        if (!res.ok) throw new Error(payload.error || `HTTP ${res.status}`)
        setBoard(toBoard(payload.cv, payload.online_work_effective))
        setCatalog(payload.catalog || null)
        setMeta({ edited: payload.edited, warnings: payload.warnings || [] })
        setState(prev => ({ ...prev, loading: false, dirty: false }))
      })
      .catch(err => setState(prev => ({ ...prev, loading: false, error: err.message })))
  }, [open, board, id])

  // Une régénération ou un retrait change la base : on relira au prochain affichage.
  useEffect(() => { queueMicrotask(() => setBoard(null)) }, [id, cvStatus?.generation?.completed_at])

  if (!hasGenerated && !edited) return null

  const disabled = locked || state.saving || state.loading
  const set = patch => {
    setBoard(prev => ({ ...prev, ...patch }))
    setState(prev => ({ ...prev, saved: false, dirty: true }))
  }
  const setList = (key, list) => set({ [key]: list })

  const save = async () => {
    setState(prev => ({ ...prev, saving: true, error: null, saved: false }))
    try {
      const res = await fetch(`/api/applications/${id}/cv/edit`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cv: fromBoard(board) }),
      })
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload.error || `HTTP ${res.status}`)
      setMeta({ edited: true, warnings: payload.warnings || [] })
      setState(prev => ({ ...prev, saving: false, saved: true, dirty: false }))
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
      setBoard(null)
      setMeta({ edited: false, warnings: [] })
      setState(prev => ({ ...prev, saving: false, dirty: false }))
      onSaved?.(id, payload)
    } catch (err) {
      setState(prev => ({ ...prev, saving: false, error: err.message || 'Retrait impossible.' }))
    }
  }

  const contact = (key, label, placeholder) => (
    <Inline value={board.contact[key]} disabled={disabled} placeholder={placeholder} label={label}
      onChange={value => set({ contact: { ...board.contact, [key]: value } })} />
  )

  return (
    <details className="consignes-details cv-editor" open={open || undefined} onToggle={e => setOpen(e.currentTarget.open)}>
      <summary>
        <PenLine /> Modifier le CV {edited ? <span className="consignes-optional">(ta version part)</span> : <span className="consignes-optional">(optionnel)</span>}
      </summary>
      <div className="consignes-editor">
        <p className="approval-note">
          Clique sur un texte pour le modifier. Attrape la poignée <GripVertical className="cvb-inline-icon" /> pour
          déplacer une rubrique, un bloc ou une puce. « Ajouter depuis ton profil » reprend une expérience, un
          projet ou un diplôme de ton profil, que tu modifies ensuite. Entrée ajoute une puce, Retour arrière sur une puce vide la supprime.
          Ta version est mise en page sans IA et remplace le CV généré à l’envoi.
        </p>
        {state.loading && <p className="approval-note">Chargement…</p>}
        {board && (
          <>
            <div className="cvb-toolbar">
              <button type="button" className="prepare-btn" disabled={disabled || !state.dirty} onClick={save}>
                {state.saving ? 'Enregistrement…' : state.dirty ? 'Enregistrer ma version' : (meta.edited || edited) ? 'Enregistré' : 'Aucune modification'}
              </button>
              {(meta.edited || edited) && (
                <>
                  <a className="copy-btn" href={`/api/applications/${id}/cv/download/cv_edit.pdf`} target="_blank" rel="noreferrer">
                    <FileDown /> Voir le PDF de ta version
                  </a>
                  <button type="button" className="annuler-btn" disabled={disabled} onClick={reset}>Revenir au CV généré</button>
                </>
              )}
              {state.dirty && <span className="cvb-dirty">Modifications non enregistrées</span>}
            </div>

            <div className="cvb-page">
              <aside className="cvb-side">
                <SideField title="Profil">
                  <Inline multiline value={board.profile} disabled={disabled} placeholder="Ton accroche en quelques lignes" label="Accroche" onChange={profile => set({ profile })} />
                </SideField>
                <SideField title="Contact">
                  {contact('email', 'Email', 'email')}
                  {contact('phone', 'Téléphone', 'téléphone')}
                  <Inline value={board.location} disabled={disabled} placeholder="ville / zone" label="Ville" onChange={location => set({ location })} />
                  {contact('portfolio', 'Site / portfolio', 'site (https://…) — vide = aucun')}
                  {contact('github', 'GitHub', 'GitHub (https://…) — vide = aucun')}
                  {contact('linkedin', 'LinkedIn', 'LinkedIn (https://…) — vide = aucun')}
                </SideField>
                <SideField title="Réalisations en ligne">
                  <Inline multiline value={board.onlineWorkText} disabled={disabled}
                    placeholder="libellé | https://… (une par ligne, vide = rubrique masquée)" label="Réalisations en ligne"
                    onChange={onlineWorkText => set({ onlineWorkText, onlineWorkCustom: true })} />
                  <p className="cvb-hint">
                    {board.onlineWorkCustom ? 'Liste choisie par toi.' : 'Calculée automatiquement — modifie-la pour la fixer.'}
                  </p>
                </SideField>
                <SideField title="Langues">
                  <Inline multiline value={board.languagesText} disabled={disabled} placeholder="Français | courant (une par ligne)" label="Langues"
                    onChange={languagesText => set({ languagesText })} />
                </SideField>
              </aside>

              <main className="cvb-main">
                <header className="cvb-header">
                  <div className="cvb-name">Facundo Varas</div>
                  <Inline className="cvb-title" value={board.title} disabled={disabled} placeholder="Titre du CV" label="Titre du CV" onChange={title => set({ title })} />
                </header>
                <DndContext
                  sensors={sensors}
                  collisionDetection={pointerFirst}
                  onDragEnd={({ active, over }) => {
                    if (!disabled && over && active.id !== over.id) {
                      set({ mainOrder: moveByKey(board.mainOrder, active.id, over.id, name => name) })
                    }
                  }}
                >
                  <SortableContext items={board.mainOrder} strategy={verticalListSortingStrategy} disabled={disabled}>
                    {board.mainOrder.map(name => (
                      <SortableBlock key={name} id={name} className="cvb-section" disabled={disabled}
                        handleLabel={`Déplacer la rubrique ${SECTION_LABELS[name]}`}>
                        <MainSection name={name} board={board} setList={setList} disabled={disabled} catalog={catalog} />
                      </SortableBlock>
                    ))}
                  </SortableContext>
                </DndContext>
              </main>
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
