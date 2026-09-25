import { Check, X } from 'lucide-react'
import './AgencyDecision.css'

/**
 * Paire segmentée « Retenu / Écarté ». L'état neutre n'est pas un troisième
 * bouton : c'est les deux au repos. Recliquer sur l'actif revient au neutre.
 */
export default function AgencyDecision({ decision, onDecide, pending = false, disabled = false }) {
  const boutons = [
    { valeur: 'retenu', Icon: Check, label: 'Retenu' },
    { valeur: 'ecarte', Icon: X, label: 'Écarté' },
  ]
  return (
    <div className="agency-decision" role="group" aria-label="Tri de cette structure">
      {boutons.map(({ valeur, Icon, label }) => (
        <button
          key={valeur}
          type="button"
          className={decision === valeur ? `is-active is-${valeur}` : ''}
          aria-pressed={decision === valeur}
          disabled={pending || disabled}
          title={decision === valeur ? `${label} — recliquer pour revenir à « à décider »` : label}
          onClick={() => onDecide(valeur)}
        >
          <Icon size={14} /> {label}
        </button>
      ))}
    </div>
  )
}
