/**
 * applicationsRepository.js — Contrat (interface) du repository de candidatures.
 *
 * PATTERN REPOSITORY — COMMENT PASSER À UNE BASE DE DONNÉES :
 * ─────────────────────────────────────────────────────────────
 * Aujourd'hui on utilise jsonApplicationsRepository.js (stockage JSON sur disque).
 * Pour migrer vers PostgreSQL, SQLite ou autre :
 *
 *   1. Crée `sqlApplicationsRepository.js` qui hérite de cette classe
 *      et implémente les 4 méthodes ci-dessous.
 *   2. Dans index.js, change UNE seule ligne :
 *        import repo from './repositories/jsonApplicationsRepository.js'
 *      → import repo from './repositories/sqlApplicationsRepository.js'
 *
 * Les routes (routes/applications.js) ne connaissent QUE cette interface.
 * Elles n'ont pas besoin de savoir si on lit du JSON ou une BDD.
 */

export default class ApplicationsRepository {
  /**
   * Retourne toutes les candidatures fusionnées avec leur statut.
   * @returns {Promise<Array>} Liste d'objets candidature enrichis
   */
  async getAll() {
    throw new Error('getAll() non implémenté');
  }

  /**
   * Retourne une candidature par son id, avec son statut.
   * @param {string} id
   * @returns {Promise<Object|null>}
   */
  async getById(id) {
    throw new Error('getById() non implémenté');
  }

  /**
   * Prépare une candidature depuis une offre issue de la recherche.
   * Génère le dossier local, met à jour candidatures.json et marque ready_to_apply.
   * @param {Object} job
   * @returns {Promise<Object>} Résultat de préparation + candidature enrichie
   */
  async prepareFromJob(job) {
    throw new Error('prepareFromJob() non implémenté');
  }

  /**
   * Marque une candidature comme postulée.
   * Écrit applied_at = aujourd'hui et follow_up_at = aujourd'hui + 7 jours.
   * @param {string} id
   * @returns {Promise<Object>} Le record mis à jour
   */
  async markApplied(id) {
    throw new Error('markApplied() non implémenté');
  }

  /**
   * Annule le statut "postulé" d'une candidature.
   * @param {string} id
   * @returns {Promise<Object>} Le record mis à jour
   */
  async markNotApplied(id) {
    throw new Error('markNotApplied() non implémenté');
  }
}
