import { describe, expect, it } from 'vitest'
import { zoneLabel, zoneOptions } from './zones'

describe('zoneLabel', () => {
  it('lit les arrondissements de Paris, Lyon et Marseille', () => {
    expect(zoneLabel('75020')).toBe('Paris 20e')
    expect(zoneLabel('75001')).toBe('Paris 1er')
    expect(zoneLabel('69003')).toBe('Lyon 3e')
    expect(zoneLabel('13008')).toBe('Marseille 8e')
  })

  it('nomme la commune quand elle est connue, le code seul sinon', () => {
    expect(zoneLabel('93100', 'Montreuil')).toBe('Montreuil (93100)')
    expect(zoneLabel('93100')).toBe('93100')
  })

  it('ne fabrique pas de zone sans code postal', () => {
    expect(zoneLabel(null, 'Paris')).toBeNull()
    expect(zoneLabel('')).toBeNull()
  })
})

describe('zoneOptions', () => {
  const lire = a => [a.cp, a.ville]

  it('compte les zones présentes et range les sans-zone en dernier', () => {
    const options = zoneOptions(
      [{ cp: '75020' }, { cp: null }, { cp: '75011' }, { cp: '75020' }],
      lire,
    )
    expect(options).toEqual([
      { value: '75011', label: 'Paris 11e', count: 1 },
      { value: '75020', label: 'Paris 20e', count: 2 },
      { value: '', label: 'Sans adresse', count: 1 },
    ])
  })

  it('accepte un libellé propre à la page pour les fiches sans zone', () => {
    const options = zoneOptions([{ cp: null }], lire, 'Sans code postal lu')
    expect(options[0]).toEqual({ value: '', label: 'Sans code postal lu', count: 1 })
  })
})
