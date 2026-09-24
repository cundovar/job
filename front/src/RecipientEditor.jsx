import { useState } from 'react'

export default function RecipientEditor({
  recipients,
  pending = false,
  saved = true,
  sendAttempt = false,
  error = null,
  onUpdate,
  onAdd,
  onRemove,
  onSave,
}) {
  const [value, setValue] = useState('')
  const canAdd = Boolean(value.trim()) && recipients.length < 5 && !sendAttempt

  return (
    <div className="recipient-editor">
      <div className="recipient-editor-head">
        <strong>Destinataires de l&apos;envoi</strong>
        <span>{recipients.length}/5</span>
      </div>
      {recipients.map((item, index) => (
        <div className="recipient-row" key={`${item.email}-${index}`}>
          <select
            value={item.role}
            onChange={event => onUpdate(index, 'role', event.target.value)}
            aria-label={`Rôle du destinataire ${index + 1}`}
            disabled={recipients.length <= 1 || sendAttempt}
            title={recipients.length <= 1
              ? 'Seule adresse de la liste : elle est le destinataire principal.'
              : 'To : le destinataire principal. Le choisir ici passe l’autre en Cc.'}
          >
            <option value="to">To</option>
            <option value="cc">Cc</option>
          </select>
          <input
            type="email"
            value={item.email}
            onChange={event => onUpdate(index, 'email', event.target.value)}
            aria-label={`Email du destinataire ${index + 1}`}
          />
          <button type="button" className="annuler-btn" onClick={() => onRemove(index)} disabled={recipients.length <= 1 || sendAttempt}>Supprimer</button>
        </div>
      ))}
      <div className="recipient-add-row">
        <input
          type="email"
          placeholder="Ajouter une adresse en Cc"
          value={value}
          onChange={event => setValue(event.target.value)}
          disabled={!canAdd && recipients.length >= 5 || sendAttempt}
        />
        <button
          type="button"
          className="annuler-btn"
          onClick={() => {
            if (!canAdd) return
            onAdd(value.trim().toLowerCase())
            setValue('')
          }}
          disabled={!canAdd}
        >Ajouter</button>
      </div>
      <button type="button" className="approve-btn" onClick={onSave} disabled={pending || sendAttempt || !recipients.length}>
        {pending ? 'Enregistrement…' : 'Enregistrer les destinataires'}
      </button>
      <p className="approval-note">
        Une adresse suffit : elle part en To. Les suivantes s’ajoutent en Cc.
      </p>
      {error && <p className="approval-note" style={{ color: '#fb7185' }}>{error}</p>}
      {!saved && <p className="approval-note">La liste a changé : enregistre-la puis réapprouve l&apos;envoi.</p>}
    </div>
  )
}
