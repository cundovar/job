import { describe, expect, it } from 'vitest'
import { boardSectionOrder, fromBoard, moveByKey, toBoard } from './cvBoard'

const CV = {
  title: 'Animateur',
  profile: 'Accroche.',
  section_order: ['profile', 'skills', 'experiences', 'projects', 'education'],
  contact: { email: 'a@b.fr' },
  location: 'Paris',
  languages: [{ name: 'Français', level: 'courant' }],
  experiences: [
    { id: 'pole_s', organization: 'Le Pôle S', title: 'Formateur', period: '2024', bullets: ['Un.', 'Deux.'], links: [] },
    { id: 'chelles', organization: 'Mairie de Chelles', title: 'Animateur', period: '2019', bullets: ['Trois.'], links: [] },
  ],
  projects: [],
  skills: [{ title: 'Animation', items: ['ateliers', 'jeux'] }],
  education: [{ year: '2010', title: 'CAP Petite Enfance', level: 'CAP', school: '', status: '' }],
}

describe('éditeur visuel du CV', () => {
  it('aller-retour CV → page → CV sans perte', () => {
    const out = fromBoard(toBoard(CV))
    expect(out.experiences.map(e => e.bullets)).toEqual([['Un.', 'Deux.'], ['Trois.']])
    expect(out.section_order).toEqual(CV.section_order)
    expect(out.education[0]).toEqual(CV.education[0])
    expect(out.skills[0].items).toEqual(['ateliers', 'jeux'])
    expect(JSON.stringify(out)).not.toContain('_key')
  })

  it('glisser une expérience la déplace', () => {
    const board = toBoard(CV)
    const [a, b] = board.experiences
    const moved = moveByKey(board.experiences, b._key, a._key)
    expect(fromBoard({ ...board, experiences: moved }).experiences.map(e => e.id)).toEqual(['chelles', 'pole_s'])
  })

  it('glisser une puce la déplace dans son expérience', () => {
    const board = toBoard(CV)
    const exp = board.experiences[0]
    const bullets = moveByKey(exp.bullets, exp.bullets[1]._key, exp.bullets[0]._key)
    const out = fromBoard({ ...board, experiences: [{ ...exp, bullets }, board.experiences[1]] })
    expect(out.experiences[0].bullets).toEqual(['Deux.', 'Un.'])
  })

  it('réordonner les rubriques garde « profile » à sa place', () => {
    const board = toBoard(CV)
    const mainOrder = moveByKey(board.mainOrder, 'education', 'skills', name => name)
    expect(boardSectionOrder({ ...board, mainOrder })).toEqual(['profile', 'education', 'skills', 'experiences', 'projects'])
  })

  it('une puce vide en cours de frappe ne part pas', () => {
    const board = toBoard(CV)
    board.experiences[0].bullets.push({ _key: 'x', text: '  ' })
    expect(fromBoard(board).experiences[0].bullets).toEqual(['Un.', 'Deux.'])
  })

  it('sans section_order, ordre par défaut', () => {
    const cv = { ...CV }
    delete cv.section_order
    expect(fromBoard(toBoard(cv)).section_order).toEqual(['profile', 'skills', 'experiences', 'projects', 'education'])
  })
})
