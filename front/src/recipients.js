/**
 * Règle des rôles d'envoi : une liste a **toujours** exactement un destinataire
 * principal (« to »), les autres sont en copie (« cc »). C'est le contrat que
 * le serveur vérifie avant d'enregistrer ; le tenir ici évite de fabriquer une
 * liste qu'il refusera, sans qu'on voie d'où vient le refus.
 */
export function setRecipientRole(items, index, role) {
  if (!Array.isArray(items) || !items[index]) return items
  if (role === 'to') {
    // Le rôle se déplace : la ligne choisie devient principale, l'ancienne passe en copie.
    return items.map((item, i) => ({ ...item, role: i === index ? 'to' : 'cc' }))
  }
  if (items[index].role !== 'to') return items
  // Rétrograder l'unique « to » : la ligne suivante prend le relais. Seule
  // adresse de la liste, elle reste principale — un envoi sans « to » n'existe pas.
  const releve = items.findIndex((_, i) => i !== index)
  if (releve === -1) return items
  return items.map((item, i) => ({ ...item, role: i === releve ? 'to' : 'cc' }))
}

/**
 * Remet la règle sur une liste qui ne la respecte pas — un brouillon resté d'une
 * version précédente, une liste relue d'ailleurs. Le premier « to » trouvé garde
 * le rôle, sinon c'est la première adresse : sans ça, un sélecteur verrouillé
 * sur une liste déjà fautive ne laisse aucun moyen d'en sortir.
 * Rend la liste **telle quelle** quand elle est déjà correcte, pour ne pas
 * fabriquer un changement à chaque rendu.
 */
export function withPrimaryRecipient(items) {
  if (!Array.isArray(items) || !items.length) return items
  const trouve = items.findIndex(item => item?.role === 'to')
  const principal = trouve === -1 ? 0 : trouve
  const correcte = items.every((item, i) => (item?.role === 'to') === (i === principal))
  return correcte ? items : items.map((item, i) => ({ ...item, role: i === principal ? 'to' : 'cc' }))
}
