import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ConsignesEditor, { ConsignesReport } from './ConsignesEditor'
import { CONSIGNE_PRESETS } from './consignes'

describe('ConsignesEditor', () => {
  afterEach(() => window.localStorage.clear())

  it('une puce ajoute sa ligne aux consignes de la lettre', () => {
    const onChange = vi.fn()
    render(<ConsignesEditor value={{ consignes: '', mailNote: 'Merci.' }} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: new RegExp(CONSIGNE_PRESETS[1]) }))
    expect(onChange).toHaveBeenCalledWith({ consignes: CONSIGNE_PRESETS[1], mailNote: 'Merci.' })
  })

  it('propose de reprendre les dernières consignes quand les champs sont vides', () => {
    window.localStorage.setItem('job.consignes.last', JSON.stringify({ consignes: 'Ton direct.', mailNote: '' }))
    const onChange = vi.fn()
    render(<ConsignesEditor value={{ consignes: '', mailNote: '' }} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: /Reprendre mes dernières consignes/ }))
    expect(onChange).toHaveBeenCalledWith({ consignes: 'Ton direct.', mailNote: '' })
  })
})

describe('ConsignesReport', () => {
  it('affiche une consigne écartée avec sa raison', () => {
    render(<ConsignesReport consignes={{
      lettre: 'Parler de Kubernetes.',
      rapport: { etat: 'rapporte', suivies: [], ecartees: [{ consigne: 'Parler de Kubernetes.', raison: 'absent du profil' }] },
    }} />)
    expect(screen.getByText(/Non suivie : Parler de Kubernetes\. — absent du profil/)).toBeInTheDocument()
  })

  it('un rapport absent invite à relire au lieu de supposer', () => {
    render(<ConsignesReport consignes={{ lettre: 'Ton direct.', rapport: { etat: 'non_rapporte' } }} />)
    expect(screen.getByText(/relis la lettre/)).toBeInTheDocument()
  })

  it('sans consigne, rien ne s’affiche', () => {
    const { container } = render(<ConsignesReport consignes={{ lettre: '', mail_note: '', rapport: {} }} />)
    expect(container).toBeEmptyDOMElement()
  })
})
