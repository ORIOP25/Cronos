import { screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CreateOrgPage from '../pages/CreateOrgPage'
import { getLegalAcceptanceStorageKey } from '../features/legal/acceptanceStorage'
import { renderWithRouter } from './testUtils'
import { resetClerkState, setClerkState } from './setup'

const mockState = vi.hoisted(() => ({
  member: { data: null, isLoading: false, isError: false },
  legal: { data: null, isLoading: false, isError: false, refetch: vi.fn() },
  run: vi.fn(),
  selectOrganization: vi.fn(),
  bootstrapActiveOrganization: vi.fn(),
  error: null,
  isPending: false,
}))

vi.mock('../features/members/data', () => ({
  useCurrentMember: () => mockState.member,
}))

vi.mock('../features/legal/data', () => ({
  useLegalStatus: () => mockState.legal,
}))

vi.mock('../features/organization/useCreateActiveOrganization', () => ({
  useCreateActiveOrganization: () => mockState,
}))

describe('CreateOrgPage', () => {
  beforeEach(() => {
    resetClerkState()
    setClerkState({ orgId: null, memberships: [] })
    mockState.run.mockReset()
    mockState.selectOrganization.mockReset()
    mockState.bootstrapActiveOrganization.mockReset()
    mockState.error = null
    mockState.isPending = false
    sessionStorage.clear()
  })

  it('renders a transition screen without a second organization form', () => {
    renderWithRouter(<CreateOrgPage />)

    expect(screen.getByRole('heading', { name: 'A preparar a sua escola' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Nome da escola')).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Criar organização' })).not.toBeInTheDocument()
  })

  it('automatically bootstraps the selected organization after legal acceptance', async () => {
    setClerkState({ orgId: 'org_new', orgName: 'Nova Escola', role: 'org:admin' })
    sessionStorage.setItem(getLegalAcceptanceStorageKey('user_test_123'), 'true')
    mockState.run.mockResolvedValue(undefined)

    renderWithRouter(<CreateOrgPage />)

    await waitFor(() => {
      expect(mockState.run).toHaveBeenCalledWith({
        name: 'Nova Escola',
        organizationId: 'org_new',
        acceptance_confirmed: true,
        returnPath: '',
      })
    })
  })

  it('does not repeat the legal acceptance warning on the transition screen', () => {
    setClerkState({ orgId: 'org_new', orgName: 'Nova Escola', role: 'org:admin' })

    renderWithRouter(<CreateOrgPage />)

    expect(screen.queryByText(/Confirme os Termos de Serviço/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Reiniciar seleção/i })).not.toBeInTheDocument()
  })
})
