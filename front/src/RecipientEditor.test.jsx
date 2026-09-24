import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import RecipientEditor from './RecipientEditor'

function renderEditor(overrides = {}) {
  const props = {
    recipients: [{ email: 'contact@example.fr', role: 'to' }],
    onUpdate: vi.fn(),
    onAdd: vi.fn(),
    onRemove: vi.fn(),
    onSave: vi.fn(),
    ...overrides,
  }
  return { ...render(<RecipientEditor {...props} />), props }
}

describe('RecipientEditor', () => {
  it('adds a Cc address and reports the new recipient', () => {
    const { props } = renderEditor()
    fireEvent.change(screen.getByPlaceholderText('Ajouter une adresse en Cc'), {
      target: { value: 'rh@example.fr' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Ajouter' }))

    expect(props.onAdd).toHaveBeenCalledWith('rh@example.fr')
  })

  it('shows the five-recipient limit and disables adding the sixth', () => {
    const recipients = Array.from({ length: 5 }, (_, index) => ({
      email: `person${index}@example.fr`,
      role: index === 0 ? 'to' : 'cc',
    }))
    renderEditor({ recipients })

    expect(screen.getByText('5/5')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ajouter' })).toBeDisabled()
  })

  it('prevents removing the last recipient', () => {
    const { props } = renderEditor()
    expect(screen.getByRole('button', { name: 'Supprimer' })).toBeDisabled()
    expect(props.onRemove).not.toHaveBeenCalled()
  })
})
