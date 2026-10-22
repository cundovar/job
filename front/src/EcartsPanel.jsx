import { TriangleAlert } from 'lucide-react'

const LABELS = { diplome: 'Diplôme', experience: 'Expérience', competence: 'Compétence', autre: 'Autre' }

// Exigences de l'annonce que ton profil ne couvre pas (demande Cundo 22/10/2026).
// Diplôme et durée sont mesurés par Python ; la compensation est une piste de
// l'IA, que le CV et la lettre exploitent sans jamais revendiquer l'absent.
export default function EcartsPanel({ ecarts }) {
  if (!Array.isArray(ecarts) || ecarts.length === 0) return null
  return (
    <section className="approval-zone ecarts-panel">
      <strong><TriangleAlert /> Écarts avec l’annonce</strong>
      <ul>
        {ecarts.map((gap, index) => (
          <li key={index}>
            <b>{LABELS[gap.type] || 'Autre'} : {gap.exigence}</b>
            {gap.profil && <> — ton profil : {gap.profil}</>}
            {gap.compensation && <p className="approval-note">Pour compenser : {gap.compensation}</p>}
            {gap.extrait && <p className="approval-note">Annonce : « {gap.extrait} »</p>}
          </li>
        ))}
      </ul>
      <p className="approval-note">
        Le CV et la lettre mettent en avant tes compétences et tes années de pratique pour compenser,
        sans jamais revendiquer un diplôme absent. À toi de juger si la candidature vaut le coup.
      </p>
    </section>
  )
}
