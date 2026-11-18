// Modèle de l'éditeur visuel du CV (demande Cundo 18/11/2026) : le CV affiché
// comme une page, rubriques et blocs déplaçables à la souris.
//
// Chaque bloc porte une clé stable (_key) pour le glisser-déposer ; les puces
// d'une expérience sont des blocs elles aussi. Rien de tout cela ne part au
// serveur : fromBoard rend la même structure que l'ancien éditeur
// (editablePayload), nettoyée côté serveur par cv_generator/user_edit.py.

import {
  csvToList,
  editablePayload,
  languagesToText,
  linesToList,
  listToCsv,
  listToLines,
  onlineWorkToText,
  textToLanguages,
  textToOnlineWork,
} from './cvEdit'

// Rubriques de la colonne principale, déplaçables. « profile » vit dans la
// colonne de gauche : sa place dans section_order n'a pas d'effet visible,
// on la conserve telle quelle.
export const MAIN_SECTIONS = ['skills', 'experiences', 'projects', 'education']
export const SECTION_LABELS = {
  skills: 'Compétences',
  experiences: 'Expériences',
  projects: 'Projets personnels',
  education: 'Formation',
}

let counter = 0
export const newKey = prefix => `${prefix}-${Date.now().toString(36)}-${(counter += 1)}`

const CONTACT_KEYS = ['email', 'phone', 'portfolio', 'github', 'linkedin']

export function mainOrder(sectionOrder) {
  const given = (Array.isArray(sectionOrder) ? sectionOrder : []).filter(name => MAIN_SECTIONS.includes(name))
  return [...given, ...MAIN_SECTIONS.filter(name => !given.includes(name))]
}

export const emptyBullet = () => ({ _key: newKey('b'), text: '' })
export const emptyExperience = () => ({
  _key: newKey('exp'), id: '', organization: '', title: '', period: '', bullets: [emptyBullet()], linksText: '',
})
export const emptyProject = () => ({
  _key: newKey('proj'), id: '', title: '', year: '', description: '', technologiesText: '', linksText: '',
})
export const emptySkill = () => ({ _key: newKey('skill'), title: '', itemsText: '' })
export const emptyEducation = () => ({ _key: newKey('edu'), year: '', title: '', level: '', school: '', status: '' })

export const ITEM_FACTORIES = {
  experiences: emptyExperience,
  projects: emptyProject,
  skills: emptySkill,
  education: emptyEducation,
}

export function toBoard(cv = {}, onlineWorkEffective = null) {
  const custom = Array.isArray(cv.online_work)
  return {
    title: cv.title || '',
    profile: cv.profile || '',
    section_order: Array.isArray(cv.section_order) ? cv.section_order : undefined,
    mainOrder: mainOrder(cv.section_order),
    contact: Object.fromEntries(CONTACT_KEYS.map(key => [key, (cv.contact || {})[key] || ''])),
    location: cv.location || '',
    languagesText: languagesToText(cv.languages),
    experiences: (cv.experiences || []).map(exp => ({
      _key: newKey('exp'),
      id: exp.id || '',
      organization: exp.organization || '',
      title: exp.title || '',
      period: exp.period || '',
      bullets: (exp.bullets || []).map(text => ({ _key: newKey('b'), text: String(text || '') })),
      linksText: listToLines(exp.links),
    })),
    projects: (cv.projects || []).map(project => ({
      _key: newKey('proj'),
      id: project.id || '',
      title: project.title || '',
      year: project.year ? String(project.year) : '',
      description: project.description || '',
      technologiesText: listToCsv(project.technologies),
      linksText: listToLines(project.links),
    })),
    skills: (cv.skills || []).map(group => ({
      _key: newKey('skill'), title: group.title || '', itemsText: listToCsv(group.items),
    })),
    education: (cv.education || []).map(edu => (typeof edu === 'string'
      ? { _key: newKey('edu'), year: '', title: edu, level: '', school: '', status: '' }
      : {
          _key: newKey('edu'),
          year: edu.year ? String(edu.year) : '',
          title: edu.title || '',
          level: edu.level || '',
          school: edu.school || '',
          status: edu.status || '',
        })),
    onlineWorkCustom: custom,
    onlineWorkText: onlineWorkToText(custom ? cv.online_work : (onlineWorkEffective || [])),
  }
}

// L'ordre des rubriques principales remplace celui de section_order, en
// gardant « profile » (et toute rubrique inconnue) à sa place d'origine.
export function boardSectionOrder(board) {
  const original = Array.isArray(board.section_order) ? board.section_order : ['profile', ...MAIN_SECTIONS]
  const queue = [...board.mainOrder]
  const merged = original.map(name => (MAIN_SECTIONS.includes(name) ? queue.shift() : name))
  return [...merged, ...queue].filter((name, i, all) => name && all.indexOf(name) === i)
}

export function fromBoard(board) {
  const cv = {
    title: board.title,
    profile: board.profile,
    section_order: boardSectionOrder(board),
    contact: Object.fromEntries(Object.entries(board.contact || {}).map(([key, value]) => [key, String(value || '').trim()])),
    location: String(board.location || '').trim(),
    languages: textToLanguages(board.languagesText),
    experiences: board.experiences.map(exp => ({
      id: exp.id,
      organization: exp.organization,
      title: exp.title,
      period: exp.period,
      bullets: exp.bullets.map(b => String(b.text || '').trim()).filter(Boolean),
      links: linesToList(exp.linksText),
    })),
    projects: board.projects.map(project => ({
      id: project.id,
      title: project.title,
      year: project.year,
      description: project.description,
      technologies: csvToList(project.technologiesText),
      links: linesToList(project.linksText),
    })),
    skills: board.skills.map(group => ({ title: group.title, items: csvToList(group.itemsText) })),
    education: board.education.map(edu => ({
      year: edu.year, title: edu.title, level: edu.level, school: edu.school, status: edu.status,
    })),
  }
  if (board.onlineWorkCustom) cv.online_work = textToOnlineWork(board.onlineWorkText)
  return editablePayload(cv)
}

/** Déplace l'élément de clé activeKey à la place de overKey (glisser-déposer). */
export function moveByKey(list, activeKey, overKey, keyOf = item => item._key) {
  const from = list.findIndex(item => keyOf(item) === activeKey)
  const to = list.findIndex(item => keyOf(item) === overKey)
  if (from < 0 || to < 0 || from === to) return list
  const next = [...list]
  const [moved] = next.splice(from, 1)
  next.splice(to, 0, moved)
  return next
}
