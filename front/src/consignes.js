// Consignes du candidat pour la lettre et le mail : puces prêtes à cocher,
// mémoire des dernières consignes (propre à ce navigateur).
//
// Une puce n'est qu'une ligne de texte dans le champ libre : cocher l'ajoute,
// décocher la retire. Le champ reste la seule source de ce qui part à l'agent,
// et l'utilisateur peut toujours reformuler à la main.

export const CONSIGNES_MAX = 2000
export const MAIL_NOTE_MAX = 1000

// Pas de puce qui affirme un fait (disponibilité, diplôme…) : une consigne
// oriente la rédaction, elle n'ajoute rien au profil du candidat.
export const CONSIGNE_PRESETS = [
  'Lettre courte : trois paragraphes au plus.',
  'Ton plus direct, moins formel.',
  "Mettre en avant l'expérience de formateur.",
  'Mettre en avant le développement web (PHP/Symfony, JavaScript).',
  'Mettre en avant WordPress et la gestion de CMS.',
  "Mettre en avant l'automatisation et l'IA (n8n, agents).",
  'Relier le parcours aux valeurs de la structure (ESS, insertion, culture).',
  'Ne pas insister sur le statut freelance.',
]

const normalize = line => line.trim().replace(/^[-•]\s*/, '')

export function hasPreset(text, preset) {
  return String(text || '').split('\n').some(line => normalize(line) === preset)
}

export function togglePreset(text, preset) {
  const lines = String(text || '').split('\n')
  if (lines.some(line => normalize(line) === preset)) {
    return lines.filter(line => normalize(line) !== preset).join('\n').replace(/^\n+|\n+$/g, '')
  }
  const base = String(text || '').replace(/\n+$/, '')
  return (base ? `${base}\n${preset}` : preset).slice(0, CONSIGNES_MAX)
}

const STORAGE_KEY = 'job.consignes.last'

// Le stockage local peut être absent (navigation privée, données effacées) :
// on ne s'y fie jamais, on rend simplement « rien de mémorisé ».
export function loadLastConsignes() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    const consignes = String(parsed?.consignes || '')
    const mailNote = String(parsed?.mailNote || '')
    return consignes.trim() || mailNote.trim() ? { consignes, mailNote } : null
  } catch {
    return null
  }
}

export function saveLastConsignes({ consignes = '', mailNote = '' } = {}) {
  try {
    if (!consignes.trim() && !mailNote.trim()) return
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ consignes, mailNote }))
  } catch {
    // Mémoire de confort seulement : un échec ne bloque rien.
  }
}
