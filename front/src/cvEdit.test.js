import { describe, expect, it } from 'vitest'
import {
  csvToList,
  editablePayload,
  fromForm,
  linesToList,
  moveItem,
  onlineWorkToText,
  textToOnlineWork,
  toForm,
} from './cvEdit'

describe('cvEdit', () => {
  it('une puce par ligne, lignes vides ignorées', () => {
    expect(linesToList(' a \n\n b ')).toEqual(['a', 'b'])
  })

  it('technologies séparées par des virgules', () => {
    expect(csvToList('Vue 3, , Symfony')).toEqual(['Vue 3', 'Symfony'])
  })

  it('déplace une expérience sans sortir de la liste', () => {
    expect(moveItem(['a', 'b', 'c'], 0, 1)).toEqual(['b', 'a', 'c'])
    expect(moveItem(['a', 'b'], 0, -1)).toEqual(['a', 'b'])
  })

  it('réalisations en ligne : aller-retour libellé | adresse', () => {
    const list = [
      { label: 'Médiateur', url: 'https://mediateur.exemple.test/' },
      { label: 'https://exemple.test', url: 'https://exemple.test' },
    ]
    expect(textToOnlineWork(onlineWorkToText(list))).toEqual(list)
  })

  it("n'envoie pas les coordonnées", () => {
    const payload = editablePayload({ title: 'T', contact: { email: 'x@y.z' }, experiences: [] })
    expect(payload.contact).toBeUndefined()
    expect(payload.title).toBe('T')
  })
})

describe('formulaire', () => {
  it('aller-retour CV → formulaire → CV sans perte', () => {
    const cv = {
      title: 'Médiateur',
      profile: 'Accroche.',
      experiences: [{ id: 'a', organization: 'Org', title: 'Poste', period: '2024', bullets: ['Un.', 'Deux.'], links: ['https://x.test'] }],
      projects: [{ id: 'p', title: 'Projet', year: 2026, description: 'Desc.', technologies: [], links: [] }],
      skills: [{ title: 'Web', items: ['PHP', 'Vue'] }],
      education: [{ year: '2012', title: 'CAP', level: '', school: '', status: '' }],
      languages: [{ name: 'Français' }],
      online_work: [{ label: 'Médiateur', url: 'https://m.test/' }],
    }
    const back = fromForm(toForm(cv))
    expect(back.experiences[0].bullets).toEqual(['Un.', 'Deux.'])
    expect(back.skills[0].items).toEqual(['PHP', 'Vue'])
    expect(back.online_work).toEqual(cv.online_work)
    expect(back.projects[0].year).toBe('2026')
  })

  it("une ligne en cours de frappe n'est pas perdue", () => {
    const form = toForm({ experiences: [{ bullets: ['Un.'] }] })
    form.experiences[0].bulletsText += '\n'
    expect(form.experiences[0].bulletsText).toBe('Un.\n')
  })

  it("sans rubrique personnalisée, online_work n'est pas envoyé", () => {
    expect(fromForm(toForm({ title: 'T', experiences: [] })).online_work).toBeUndefined()
  })
})
