import { describe, expect, it } from 'vitest'
import { addSkillToBoard, availableFromCatalog, availableSkills, boardSectionOrder, catalogEntryToItem, fromBoard, moveByKey, toBoard } from './cvBoard'

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

describe('profil : entrées à ajouter', () => {
  const catalog = {
    experiences: [
      { id: 'pole_s', organization: 'Le Pôle S', title: 'Formateur', period: '2024', bullets: ['Un.'], links: [] },
      { id: 'bioconcept', organization: 'Bioconcept', title: 'Gardien / Hôte d’accueil', period: '2023 – 2025', bullets: ['Accueil.'], links: [] },
    ],
    projects: [{ id: 'mediateur', title: 'Mediateur', year: '2026', description: 'Site.', technologies: ['Vue'], links: [] }],
    education: [
      { year: '2010', title: 'CAP petite enfance' },
      { year: '2026', title: 'Titre Professionnel CDA', level: 'niveau 6', status: 'VAE en cours' },
    ],
  }

  it('propose seulement ce qui n’est pas déjà sur la page', () => {
    const board = toBoard(CV)
    expect(availableFromCatalog(catalog, board, 'experiences').map(e => e.id)).toEqual(['bioconcept'])
    expect(availableFromCatalog(catalog, board, 'projects').map(e => e.id)).toEqual(['mediateur'])
    // diplômes reconnus par l'intitulé, sans tenir compte de la casse
    expect(availableFromCatalog(catalog, board, 'education').map(e => e.title)).toEqual(['Titre Professionnel CDA'])
  })

  it('un diplôme ajouté garde son statut', () => {
    const board = toBoard(CV)
    const item = catalogEntryToItem('education', catalog.education[1])
    const out = fromBoard({ ...board, education: [...board.education, item] })
    expect(out.education.at(-1)).toEqual({ year: '2026', title: 'Titre Professionnel CDA', level: 'niveau 6', school: '', status: 'VAE en cours' })
  })

  it('une entrée ajoutée devient un bloc modifiable et part au serveur', () => {
    const board = toBoard(CV)
    const item = catalogEntryToItem('experiences', catalog.experiences[1])
    expect(item._key).toBeTruthy()
    item.title = 'Hôte d’accueil'
    const out = fromBoard({ ...board, experiences: [...board.experiences, item] })
    expect(out.experiences.at(-1)).toMatchObject({ id: 'bioconcept', title: 'Hôte d’accueil', bullets: ['Accueil.'] })
  })
})

describe('profil : compétences à ajouter', () => {
  const catalog = { skills: [{ name: 'Jeux', level: 'pratique' }, { name: 'Gestion de conflits', level: 'pratique' }] }

  it('propose les compétences absentes de tous les groupes', () => {
    expect(availableSkills(catalog, toBoard(CV)).map(s => s.name)).toEqual(['Gestion de conflits'])
  })

  it('ajoute au groupe choisi ou crée un groupe', () => {
    const board = toBoard(CV)
    const inGroup = addSkillToBoard(board.skills, 0, 'Gestion de conflits')
    expect(fromBoard({ ...board, skills: inGroup }).skills[0].items).toEqual(['ateliers', 'jeux', 'Gestion de conflits'])
    const newGroup = addSkillToBoard(board.skills, -1, 'Gestion de conflits')
    expect(fromBoard({ ...board, skills: newGroup }).skills.at(-1)).toEqual({ title: 'Autres compétences', items: ['Gestion de conflits'] })
  })
})
