import { describe, expect, it } from 'vitest'
import { setRecipientRole, withPrimaryRecipient } from './recipients'

const roles = items => items.map(item => item.role)

describe('setRecipientRole', () => {
  const trois = [
    { email: 'a@x.fr', role: 'to' },
    { email: 'b@x.fr', role: 'cc' },
    { email: 'c@x.fr', role: 'cc' },
  ]

  it('déplace le rôle principal au lieu de le dupliquer', () => {
    expect(roles(setRecipientRole(trois, 2, 'to'))).toEqual(['cc', 'cc', 'to'])
  })

  it('confie le rôle principal à la ligne suivante quand on rétrograde le « to »', () => {
    expect(roles(setRecipientRole(trois, 0, 'cc'))).toEqual(['cc', 'to', 'cc'])
  })

  it('laisse la seule adresse de la liste en destinataire principal', () => {
    const seule = [{ email: 'a@x.fr', role: 'to' }]
    // Sans quoi on obtenait une liste sans « to », que le serveur refuse
    // d'enregistrer — le blocage constaté sur une candidature à une adresse.
    expect(setRecipientRole(seule, 0, 'cc')).toBe(seule)
  })

  it('ne touche à rien quand un « cc » est remis en « cc »', () => {
    expect(setRecipientRole(trois, 1, 'cc')).toBe(trois)
  })
})

describe('withPrimaryRecipient', () => {
  it('rend la liste telle quelle quand elle respecte déjà la règle', () => {
    const items = [{ email: 'a@x.fr', role: 'to' }, { email: 'b@x.fr', role: 'cc' }]
    expect(withPrimaryRecipient(items)).toBe(items)
  })

  it('répare une liste sans destinataire principal', () => {
    // Le cas vécu : une seule adresse laissée en Cc, impossible à enregistrer
    // et — sélecteur verrouillé — impossible à corriger à la main.
    expect(withPrimaryRecipient([{ email: 'epn@ageca.org', role: 'cc' }]))
      .toEqual([{ email: 'epn@ageca.org', role: 'to' }])
  })

  it('garde le premier « to » quand plusieurs se disputent le rôle', () => {
    const items = [
      { email: 'a@x.fr', role: 'cc' },
      { email: 'b@x.fr', role: 'to' },
      { email: 'c@x.fr', role: 'to' },
    ]
    expect(withPrimaryRecipient(items).map(i => i.role)).toEqual(['cc', 'to', 'cc'])
  })

  it('laisse une liste vide vide', () => {
    expect(withPrimaryRecipient([])).toEqual([])
  })
})
