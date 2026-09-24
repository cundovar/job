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

  it('locks the role when a single address is listed', () => {
    // Une seule adresse : elle est forcément le destinataire principal. La
    // passer en Cc fabriquait une liste sans « to », refusée à l'enregistrement.
    renderEditor()
    expect(screen.getByRole('combobox', { name: 'Rôle du destinataire 1' })).toBeDisabled()
  })

  it('leaves the role selectable as soon as there are two addresses', () => {
    renderEditor({ recipients: [
      { email: 'contact@example.fr', role: 'to' },
      { email: 'rh@example.fr', role: 'cc' },
    ] })
    expect(screen.getByRole('combobox', { name: 'Rôle du destinataire 2' })).toBeEnabled()
  })

  it('prevents removing the last recipient', () => {
    const { props } = renderEditor()
    expect(screen.getByRole('button', { name: 'Supprimer' })).toBeDisabled()
    expect(props.onRemove).not.toHaveBeenCalled()
  })
})
