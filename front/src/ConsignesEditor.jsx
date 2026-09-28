import { useState } from 'react'
import { Check, CircleCheck, History, TriangleAlert } from 'lucide-react'
import {
  CONSIGNES_MAX,
  CONSIGNE_PRESETS,
  MAIL_NOTE_MAX,
  hasPreset,
  loadLastConsignes,
  togglePreset,
} from './consignes'

// Consignes optionnelles pour la lettre (lues par l'agent) et phrase perso
// pour le mail (insérée telle quelle). Tout vide = génération habituelle.
export default function ConsignesEditor({ value, onChange, disabled = false }) {
  const consignes = value?.consignes || ''
  const mailNote = value?.mailNote || ''
  const [last] = useState(() => loadLastConsignes())
  const set = patch => onChange({ consignes, mailNote, ...patch })
  const canRecall = last && !consignes.trim() && !mailNote.trim()

  return (
    <div className="consignes-editor">
      <div className="consignes-chips" role="group" aria-label="Consignes rapides">
        {CONSIGNE_PRESETS.map(preset => {
          const active = hasPreset(consignes, preset)
          return (
            <button
              key={preset}
              type="button"
              className={`consigne-chip ${active ? 'active' : ''}`}
              aria-pressed={active}
              disabled={disabled}
              onClick={() => set({ consignes: togglePreset(consignes, preset) })}
            >
              {active && <Check />} {preset}
            </button>
          )
        })}
      </div>

      <label className="consignes-label">
        Pour la lettre
        <textarea
          className="agency-consignes"
          rows={3}
          maxLength={CONSIGNES_MAX}
          value={consignes}
          disabled={disabled}
          onChange={e => set({ consignes: e.target.value })}
          placeholder="Optionnel : ce que tu veux mettre en avant, le ton, ce qu'il faut éviter… L'IA ne s'en sert que si ton profil le permet."
        />
      </label>

      <label className="consignes-label">
        Phrase perso pour le mail
        <textarea
          className="agency-consignes"
          rows={2}
          maxLength={MAIL_NOTE_MAX}
          value={mailNote}
          disabled={disabled}
          onChange={e => set({ mailNote: e.target.value })}
          placeholder="Optionnel : une phrase à toi, ajoutée telle quelle au mail (ex. « J'ai découvert votre projet X lors de… »)."
        />
      </label>

      {canRecall && (
        <button
          type="button"
          className="copy-btn consignes-recall"
          disabled={disabled}
          onClick={() => onChange({ consignes: last.consignes, mailNote: last.mailNote })}
        >
          <History /> Reprendre mes dernières consignes
        </button>
      )}
    </div>
  )
}

// Ce que le candidat a demandé et ce que l'agent dit en avoir fait. Un
// rapport absent n'est pas un succès : on invite à relire.
export function ConsignesReport({ consignes }) {
  if (!consignes) return null
  const { lettre = '', mail_note: mailNote = '', rapport = {} } = consignes
  if (!lettre.trim() && !mailNote.trim()) return null
  const suivies = rapport.suivies || []
  const ecartees = rapport.ecartees || []

  return (
    <div className="consignes-report">
      <strong>Tes consignes pour ce dossier</strong>
      {lettre.trim() && <pre className="consignes-text">{lettre}</pre>}
      {mailNote.trim() && (
        <p className="consignes-mail-note">
          Phrase ajoutée telle quelle au mail : « {mailNote} »
        </p>
      )}
      {lettre.trim() && rapport.etat === 'rapporte' && (
        <>
          {suivies.length > 0 && (
            <ul className="consignes-suivies">
              {suivies.map((item, idx) => <li key={idx}><CircleCheck /> {item}</li>)}
            </ul>
          )}
          {ecartees.length > 0 && (
            <ul className="consignes-ecartees">
              {ecartees.map((item, idx) => (
                <li key={idx}>
                  <TriangleAlert /> Non suivie : {item.consigne}
                  {item.raison && <> — {item.raison}</>}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      {lettre.trim() && rapport.etat !== 'rapporte' && (
        <p className="consignes-unknown">
          <TriangleAlert /> L'agent n'a pas indiqué ce qu'il a fait de tes consignes : relis la lettre pour vérifier.
        </p>
      )}
    </div>
  )
}
