import { afterEach, describe, expect, it } from 'vitest'
import {
  CONSIGNE_PRESETS,
  hasPreset,
  loadLastConsignes,
  saveLastConsignes,
  togglePreset,
} from './consignes'

const preset = CONSIGNE_PRESETS[0]

describe('puces de consignes', () => {
  it('cocher ajoute la ligne sans toucher au texte libre', () => {
    const text = togglePreset('Parler du projet DevDoc.', preset)
    expect(text).toBe(`Parler du projet DevDoc.\n${preset}`)
    expect(hasPreset(text, preset)).toBe(true)
  })

  it('décocher retire la ligne, même précédée d’un tiret', () => {
    const text = togglePreset(`- ${preset}\nParler du projet DevDoc.`, preset)
    expect(text).toBe('Parler du projet DevDoc.')
    expect(hasPreset(text, preset)).toBe(false)
  })

  it('un champ vide reçoit la puce seule', () => {
    expect(togglePreset('', preset)).toBe(preset)
  })
})

describe('mémoire des dernières consignes', () => {
  afterEach(() => window.localStorage.clear())

  it('relit ce qui a été mémorisé', () => {
    saveLastConsignes({ consignes: 'Ton direct.', mailNote: 'Merci.' })
    expect(loadLastConsignes()).toEqual({ consignes: 'Ton direct.', mailNote: 'Merci.' })
  })

  it('ne mémorise pas des champs vides (ne pas effacer les précédentes)', () => {
    saveLastConsignes({ consignes: 'Ton direct.', mailNote: '' })
    saveLastConsignes({ consignes: '  ', mailNote: '' })
    expect(loadLastConsignes()?.consignes).toBe('Ton direct.')
  })

  it('un stockage corrompu rend « rien de mémorisé »', () => {
    window.localStorage.setItem('job.consignes.last', '{pas du json')
    expect(loadLastConsignes()).toBeNull()
  })
})
