/**
 * Zones d'affichage — partagées par les deux onglets Agences.
 *
 * Un code postal est **lu** dans une adresse, jamais déduit : une fiche qui n'en
 * porte pas se range à part au lieu d'être rattachée d'office au périmètre
 * cherché. Ce regroupement ne dit rien de la provenance de la position : c'est
 * `how` (V2) qui le dit, et il reste affiché sur chaque ligne.
 */

// Ces trois villes sont découpées en arrondissements : « 75020 » se lit « Paris 20e ».
const ARRONDISSEMENTS = { 75: 'Paris', 69: 'Lyon', 13: 'Marseille' }

export function zoneLabel(cp, ville) {
  if (!cp) return null
  const base = ARRONDISSEMENTS[cp.slice(0, 2)]
  const rang = Number(cp.slice(2))
  if (base && rang >= 1 && rang <= 20) return `${base} ${rang}${rang === 1 ? 'er' : 'e'}`
  return ville ? `${ville} (${cp})` : cp
}

/**
 * Les zones **réellement présentes** dans la liste, comptées. Une liste
 * théorique ferait proposer des arrondissements vides ; un vide se relirait
 * comme « rien ici », alors qu'il n'y a simplement rien eu à lire.
 */
export function zoneOptions(items, read, labelSansZone = 'Sans adresse') {
  const zones = new Map()
  for (const item of items || []) {
    const [cp, ville] = read(item)
    const cle = cp || ''
    const entry = zones.get(cle)
      || { value: cle, label: zoneLabel(cp, ville) || labelSansZone, count: 0 }
    entry.count += 1
    zones.set(cle, entry)
  }
  // Les vraies zones d'abord, par code postal ; les fiches sans zone en dernier.
  return [...zones.values()].sort((a, b) =>
    a.value === '' ? 1 : b.value === '' ? -1 : a.value.localeCompare(b.value))
}
