import { useLocation } from 'react-router-dom'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LegalAcceptancePage from '../pages/LegalAcceptancePage'
import { renderWithRouter } from './testUtils'

const mockState = vi.hoisted(() => ({
  member: null,
  legal: null,
  mutateAsync: vi.fn(),
}))

vi.mock('../features/members/data', () => ({
  useCurrentMember: () => mockState.member,
}))

vi.mock('../features/legal/data', () => ({
  useLegalStatus: () => mockState.legal,
  useAcceptLegalDocuments: () => ({ isPending: false, mutateAsync: mockState.mutateAsync }),
}))

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}</output>
}

function renderPage() {
  return renderWithRouter(<><LegalAcceptancePage /><LocationProbe /></>, {
    initialEntries: [{ pathname: '/legal/aceitar', state: { from: '/dashboard' } }],
  })
}

describe('LegalAcceptancePage', () => {
  beforeEach(() => {
    mockState.member = {
      data: {
        capabilities: ['admin'],
        foundation_status: 'COMPLETED',
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    }
    mockState.legal = {
      data: {
        accepted: false,
        requires_acceptance: true,
        terms_version: '2026-01',
        dpa_version: '2026-01',
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    }
    mockState.mutateAsync.mockReset()
    mockState.mutateAsync.mockResolvedValue({ accepted: true })
  })

  it('requires all confirmations before submitting', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(screen.getByRole('button', { name: 'Aceitar e continuar' }))

    expect(screen.getByRole('alert')).toHaveTextContent(/autoridade/i)
    expect(mockState.mutateAsync).not.toHaveBeenCalled()
  })

  it('submits the current versions and returns to the safe internal route', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.type(screen.getByLabelText('Nome legal da entidade'), 'Entidade Teste')
    await user.type(screen.getByLabelText('NIF/NIPC'), '999999990')
    await user.type(screen.getByLabelText('Morada registada'), 'Rua de Teste, 1')
    await user.type(screen.getByLabelText('Email de contacto'), 'legal@test.com')
    await user.type(screen.getByLabelText('Nome do representante'), 'Representante')
    await user.type(screen.getByLabelText('Cargo do representante'), 'Administrador')
    for (const label of [
      'Confirmo que tenho poderes para vincular esta organização.',
      /Li e aceito os Termos de Serviço/,
      /Li e aceito o Acordo de Tratamento de Dados/,
    ]) await user.click(screen.getByLabelText(label))

    await user.click(screen.getByRole('button', { name: 'Aceitar e continuar' }))

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/dashboard'))
    expect(mockState.mutateAsync).toHaveBeenCalledWith(expect.objectContaining({
      controller_legal_name: 'Entidade Teste',
      terms_version: '2026-01',
      dpa_version: '2026-01',
      terms_accepted: true,
      dpa_accepted: true,
    }))
  })

  it('shows the administrator-only state to non-admin members', () => {
    mockState.member.data.capabilities = ['teacher']
    renderPage()

    expect(screen.getByText(/Um administrador autorizado/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Aceitar e continuar' })).not.toBeInTheDocument()
  })

  it('renders a retry action when the legal state cannot be loaded', () => {
    mockState.legal.isError = true
    renderPage()

    expect(screen.getByRole('alert')).toHaveTextContent(/não foi possível verificar/i)
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    expect(mockState.legal.refetch).toHaveBeenCalledOnce()
  })
})
