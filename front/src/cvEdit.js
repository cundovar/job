// Aides de l'éditeur de CV : conversions entre les champs de saisie (une puce
// par ligne, des technologies séparées par des virgules) et la structure du CV.
// La version est nettoyée côté serveur (cv_generator/user_edit.py) : ici on ne
// fait que la mettre en forme.

export const linesToList = text => String(text || '').split('\n').map(line => line.trim()).filter(Boolean)
export const listToLines = list => (Array.isArray(list) ? list : []).join('\n')
export const csvToList = text => String(text || '').split(',').map(item => item.trim()).filter(Boolean)
export const listToCsv = list => (Array.isArray(list) ? list : []).join(', ')

export function moveItem(list, index, delta) {
  const next = [...list]
  const target = index + delta
  if (target < 0 || target >= next.length) return next
  ;[next[index], next[target]] = [next[target], next[index]]
  return next
}

export const removeItem = (list, index) => list.filter((_, i) => i !== index)
export const replaceItem = (list, index, patch) => list.map((item, i) => (i === index ? { ...item, ...patch } : item))

// « Libellé | https://… » une réalisation par ligne ; une ligne sans « | » est
// une adresse seule, affichée telle quelle.
export function textToOnlineWork(text) {
  return linesToList(text).map(line => {
    const [left, ...rest] = line.split('|')
    if (!rest.length) return { label: left.trim(), url: left.trim() }
    return { label: left.trim(), url: rest.join('|').trim() }
  }).filter(item => item.url)
}

export function onlineWorkToText(list) {
  return (Array.isArray(list) ? list : [])
    .map(item => (item.label && item.label !== item.url ? `${item.label} | ${item.url}` : item.url))
    .join('\n')
}


// Ce qui part au serveur : seulement les champs éditables.
export function editablePayload(cv) {
  const payload = {
    title: cv.title || '',
    profile: cv.profile || '',
    section_order: cv.section_order,
    experiences: cv.experiences || [],
    projects: cv.projects || [],
    skills: cv.skills || [],
    education: cv.education || [],
    languages: cv.languages || [],
  }
  if (cv.contact && typeof cv.contact === 'object') payload.contact = cv.contact
  if (typeof cv.location === 'string') payload.location = cv.location
  if (Array.isArray(cv.online_work)) payload.online_work = cv.online_work
  return payload
}

// « Français | courant », une langue par ligne.
export function textToLanguages(text) {
  return linesToList(text).map(line => {
    const [name, ...rest] = line.split('|')
    const level = rest.join('|').trim()
    return level ? { name: name.trim(), level } : { name: name.trim() }
  }).filter(item => item.name)
}

export function languagesToText(list) {
  return (Array.isArray(list) ? list : [])
    .map(item => (typeof item === 'string' ? item : (item.level ? `${item.name} | ${item.level}` : item.name || '')))
    .filter(Boolean)
    .join('\n')
}

const CONTACT_KEYS = ['email', 'phone', 'portfolio', 'github', 'linkedin']

// Le formulaire garde le texte brut des champs multi-lignes : convertir à
// chaque frappe mangerait le retour à la ligne qu'on est en train de taper.
export function toForm(cv = {}, onlineWorkEffective = null) {
  const custom = Array.isArray(cv.online_work)
  return {
    title: cv.title || '',
    profile: cv.profile || '',
    section_order: cv.section_order,
    contact: Object.fromEntries(CONTACT_KEYS.map(key => [key, (cv.contact || {})[key] || ''])),
    location: cv.location || '',
    languagesText: languagesToText(cv.languages),
    experiences: (cv.experiences || []).map(exp => ({
      id: exp.id || '',
      organization: exp.organization || '',
      title: exp.title || '',
      period: exp.period || '',
      bulletsText: listToLines(exp.bullets),
      linksText: listToLines(exp.links),
    })),
    projects: (cv.projects || []).map(project => ({
      id: project.id || '',
      title: project.title || '',
      year: project.year ? String(project.year) : '',
      description: project.description || '',
      technologiesText: listToCsv(project.technologies),
      linksText: listToLines(project.links),
    })),
    skills: (cv.skills || []).map(group => ({ title: group.title || '', itemsText: listToCsv(group.items) })),
    education: (cv.education || []).map(edu => (typeof edu === 'string'
      ? { year: '', title: edu, level: '', school: '', status: '' }
      : { year: edu.year ? String(edu.year) : '', title: edu.title || '', level: edu.level || '', school: edu.school || '', status: edu.status || '' })),
    // La rubrique telle qu'elle s'affiche : choisie par toi, ou à défaut celle
    // que la mise en page calcule. La modifier la rend « choisie par toi ».
    onlineWorkCustom: custom,
    onlineWorkText: onlineWorkToText(custom ? cv.online_work : (onlineWorkEffective || [])),
  }
}

export function fromForm(form) {
  const cv = {
    title: form.title,
    profile: form.profile,
    section_order: form.section_order,
    contact: Object.fromEntries(Object.entries(form.contact || {}).map(([key, value]) => [key, String(value || '').trim()])),
    location: String(form.location || '').trim(),
    languages: textToLanguages(form.languagesText),
    experiences: form.experiences.map(exp => ({
      id: exp.id,
      organization: exp.organization,
      title: exp.title,
      period: exp.period,
      bullets: linesToList(exp.bulletsText),
      links: linesToList(exp.linksText),
    })),
    projects: form.projects.map(project => ({
      id: project.id,
      title: project.title,
      year: project.year,
      description: project.description,
      technologies: csvToList(project.technologiesText),
      links: linesToList(project.linksText),
    })),
    skills: form.skills.map(group => ({ title: group.title, items: csvToList(group.itemsText) })),
    education: form.education,
  }
  if (form.onlineWorkCustom) cv.online_work = textToOnlineWork(form.onlineWorkText)
  return editablePayload(cv)
}

export const emptyExperienceForm = () => ({ id: '', organization: '', title: '', period: '', bulletsText: '', linksText: '' })
export const emptyProjectForm = () => ({ id: '', title: '', year: '', description: '', technologiesText: '', linksText: '' })
export const emptySkillForm = () => ({ title: '', itemsText: '' })
export const emptyEducationForm = () => ({ year: '', title: '', level: '', school: '', status: '' })
