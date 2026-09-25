import { describe, expect, it } from 'vitest'
import { A_DECIDER, decisionCounts, domainKey, matchesDecision } from './agencyDecisions'

describe('domainKey', () => {
  it('ramène les écritures d’un même site à une seule clé', () => {
    // La carte V2 lit « www.exemple.fr » dans l'URL, le scout stocke
    // « exemple.fr » : sans normalisation, deux agences pour une.
    expect(domainKey('https://www.exemple.fr/contact')).toBe('exemple.fr')
    expect(domainKey('EXEMPLE.FR')).toBe('exemple.fr')
    expect(domainKey('')).toBe('')
    expect(domainKey(null)).toBe('')
  })
})

describe('decisionCounts', () => {
  it('compte les trois états, l’absence de décision comprise', () => {
    const items = [{ d: 'retenu' }, { d: 'ecarte' }, { d: '' }, { d: 'retenu' }, { d: 'inconnu' }]

    // Une valeur inconnue n'est pas une décision : elle reste à décider.
    expect(decisionCounts(items, i => i.d)).toEqual({
      retenu: 2, ecarte: 1, [A_DECIDER]: 2, toutes: 5,
    })
  })
})

describe('matchesDecision', () => {
  it('ne cache rien tant qu’aucun filtre n’est choisi', () => {
    expect(matchesDecision('', '')).toBe(true)
    expect(matchesDecision('ecarte', '')).toBe(true)
  })

  it('range les fiches sans décision sous « à décider »', () => {
    expect(matchesDecision('', A_DECIDER)).toBe(true)
    expect(matchesDecision('retenu', A_DECIDER)).toBe(false)
  })

  it('filtre sur la décision exacte', () => {
    expect(matchesDecision('ecarte', 'ecarte')).toBe(true)
    expect(matchesDecision('retenu', 'ecarte')).toBe(false)
  })
})
