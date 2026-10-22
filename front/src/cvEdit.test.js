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

  it('envoie les coordonnées revues par le candidat', () => {
    const payload = editablePayload({ title: 'T', contact: { email: 'x@y.z' }, location: 'Paris', experiences: [] })
    expect(payload.contact).toEqual({ email: 'x@y.z' })
    expect(payload.location).toBe('Paris')
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
    expect(back.languages).toEqual([{ name: 'Français' }])
  })

  it('langues : « nom | niveau », une par ligne', () => {
    const form = toForm({ languages: [{ name: 'Français', level: 'courant' }, { name: 'Anglais', level: 'technique' }] })
    expect(form.languagesText).toBe('Français | courant\nAnglais | technique')
    form.languagesText += '\nEspagnol'
    expect(fromForm(form).languages).toEqual([
      { name: 'Français', level: 'courant' }, { name: 'Anglais', level: 'technique' }, { name: 'Espagnol' },
    ])
  })

  it('coordonnées modifiables, champ vidé envoyé vide', () => {
    const form = toForm({ contact: { email: 'a@b.fr', phone: '06 00', portfolio: 'https://m.test/' }, location: 'Paris' })
    form.contact.phone = ''
    form.location = 'Montreuil'
    const back = fromForm(form)
    expect(back.contact).toEqual({ email: 'a@b.fr', phone: '', portfolio: 'https://m.test/', github: '', linkedin: '' })
    expect(back.location).toBe('Montreuil')
  })

  it('réalisations : la liste affichée sert de départ, sans être imposée', () => {
    const effective = [{ label: 'mediateur.test', url: 'https://mediateur.test/' }]
    const form = toForm({ title: 'T', experiences: [] }, effective)
    expect(form.onlineWorkText).toBe('mediateur.test | https://mediateur.test/')
    expect(fromForm(form).online_work).toBeUndefined()
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
