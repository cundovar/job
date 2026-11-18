// Présentation d'un dossier : site web affiché ou non, adresse, titre de la
// signature du mail HTML. La règle et les défauts vivent côté Python
// (utils/presentation.py) ; ici, seulement la mise en forme des choix.

export const WEBSITE_CHOICES = [
  'varascundo.com',
  'mediateur.varascundo.com',
  'devdoc.varascundo.com',
  'ia.varascundo.com',
]

export const TITLE_MAX = 120
export const URL_MAX = 200

// Avant génération : « auto » laisse la famille du poste décider.
export const EMPTY_PREPARE_PRESENTATION = { site: 'auto', websiteUrl: '', displayTitle: '' }

/** Champs à ajouter à l'offre envoyée à /api/applications/prepare. */
export function presentationToJob(value) {
  const v = value || EMPTY_PREPARE_PRESENTATION
  const out = {}
  if (v.site === 'yes') out.show_website = true
  if (v.site === 'no') out.show_website = false
  const url = (v.websiteUrl || '').trim().slice(0, URL_MAX)
  if (v.site === 'yes' && url) out.website_url = url
  const title = (v.displayTitle || '').trim().slice(0, TITLE_MAX)
  if (title) out.display_title = title
  return out
}

/** Vrai si l'utilisateur a changé quelque chose par rapport à « automatique ». */
export function hasPresentationChoice(value) {
  return Object.keys(presentationToJob(value)).length > 0
}
