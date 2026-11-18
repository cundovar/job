import { EMPTY_PREPARE_PRESENTATION, TITLE_MAX, URL_MAX, WEBSITE_CHOICES } from './presentation'

// Choix avant génération : site web (auto / oui / non), adresse, titre du mail.
// « Automatique » = défaut selon la famille du poste (site pour le dev, rien
// pour l'accueil, l'animation, la médiation…).
export default function PresentationFields({ value, onChange, disabled = false }) {
  const v = value || EMPTY_PREPARE_PRESENTATION
  const set = patch => onChange({ ...v, ...patch })

  return (
    <div className="presentation-fields">
      <label className="consignes-label">
        Site web dans la lettre et le mail
        <select
          value={v.site}
          disabled={disabled}
          onChange={e => set({ site: e.target.value })}
        >
          <option value="auto">Automatique selon le poste</option>
          <option value="yes">Oui, ajouter un site web</option>
          <option value="no">Non, aucun site</option>
        </select>
      </label>
      {v.site === 'yes' && (
        <label className="consignes-label">
          Site affiché
          <input
            type="text"
            list="presentation-site-choices"
            maxLength={URL_MAX}
            value={v.websiteUrl}
            disabled={disabled}
            placeholder="varascundo.com"
            onChange={e => set({ websiteUrl: e.target.value })}
          />
          <datalist id="presentation-site-choices">
            {WEBSITE_CHOICES.map(site => <option key={site} value={site} />)}
          </datalist>
        </label>
      )}
      <label className="consignes-label">
        Titre sous ton nom (signature du mail)
        <input
          type="text"
          maxLength={TITLE_MAX}
          value={v.displayTitle}
          disabled={disabled}
          placeholder="Automatique selon le poste — ex. « Animateur – accueil des publics »"
          onChange={e => set({ displayTitle: e.target.value })}
        />
      </label>
    </div>
  )
}
