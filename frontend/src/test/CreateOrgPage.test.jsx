import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CreateOrgPage from '../pages/CreateOrgPage'
import { renderWithProviders, renderWithRouter } from './testUtils'
import { resetClerkState, setClerkState } from './setup'

const mockState = vi.hoisted(() => ({
  member: null,
  legal: null,
  acceptance: {
    mutateAsync: vi.fn(),
    isPending: false,
    error: null,
  },
  bootstrapActiveOrganization: vi.fn(),
  bootstrapPending: false,
  bootstrapError: null,
}))

vi.mock('../features/members/data', () => ({
  useCurrentMember: () => mockState.member,
}))

vi.mock('../features/legal/data', () => ({
  useLegalStatus: () => mockState.legal,
  useAcceptLegalDocuments: () => mockState.acceptance,
}))

vi.mock('../features/organization/useCreateActiveOrganization', () => ({
  useCreateActiveOrganization: () => ({
    bootstrapActiveOrganization: mockState.bootstrapActiveOrganization,
    isPending: mockState.bootstrapPending,
    error: mockState.bootstrapError,
  }),
}))

const adminMember = {
  member_id: 8,
  access_status: 'active',
  lifecycle_status: 'active',
  capabilities: ['admin'],
  default_mode: 'admin',
  foundation_status: 'NOT_STARTED',
}

const teacherMember = {
  ...adminMember,
  capabilities: ['teacher'],
  default_mode: 'teacher',
}

const legalStatus = {
  accepted: false,
  requires_acceptance: true,
  terms_version: '2026-01',
  dpa_version: '2026-01',
  privacy_version: '2026-01',
  accepted_at: null,
}

beforeEach(() => {
  resetClerkState()
  setClerkState({ orgId: null, memberships: [] })
  mockState.member = {
    data: null,
    isLoading: false,
    isError: false,
    isSuccess: false,
    error: null,
    refetch: vi.fn(),
  }
  mockState.legal = {
    data: null,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }
  mockState.acceptance = {
    mutateAsync: vi.fn().mockResolvedValue({}),
    isPending: false,
    error: null,
  }
  mockState.bootstrapActiveOrganization.mockReset()
  mockState.bootstrapActiveOrganization.mockResolvedValue(undefined)
  mockState.bootstrapPending = false
  mockState.bootstrapError = null
})

describe('CreateOrgPage', () => {
  it('shows the organization switcher and a real Clerk task action without an active organization', async () => {
    const user = userEvent.setup()
    renderWithRouter(<CreateOrgPage />)

    expect(screen.getByTestId('organization-switcher')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retomar tarefa de organização' })).toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retomar tarefa de organização' }))
  })

  it('bootstraps an active organization with no local member once', async () => {
    setClerkState({ orgId: 'org_new', orgName: 'Nova Escola', role: 'org:admin' })
    mockState.member = {
      data: null,
      isLoading: false,
      isError: true,
      isSuccess: false,
      error: { response: { status: 403 } },
      refetch: vi.fn(),
    }

    renderWithRouter(<CreateOrgPage />)

    await waitFor(() => expect(mockState.bootstrapActiveOrganization).toHaveBeenCalledTimes(1))
  })

  it('requires the exact confirmation before posting all current document versions', async () => {
    const user = userEvent.setup()
    setClerkState({ orgId: 'org_legal', orgName: 'Escola Legal', role: 'org:admin' })
    mockState.member = { data: adminMember, isLoading: false, isError: false, isSuccess: true }
    mockState.legal = { data: legalStatus, isLoading: false, isError: false, refetch: vi.fn() }

    renderWithRouter(<CreateOrgPage />)

    const checkbox = screen.getByRole('checkbox', { name: /Confirmo que tenho poderes para vincular a organização/ })
    const button = screen.getByRole('button', { name: 'Confirmar e continuar' })
    expect(checkbox).not.toBeChecked()
    expect(button).toBeDisabled()

    await user.click(checkbox)
    expect(button).toBeEnabled()
    await user.click(button)

    expect(mockState.acceptance.mutateAsync).toHaveBeenCalledWith({
      acceptance_confirmed: true,
      terms_version: '2026-01',
      dpa_version: '2026-01',
      privacy_version: '2026-01',
    })
    expect(screen.getByRole('link', { name: 'Termos de Serviço' })).toHaveTextContent('Termos de Serviço')
    expect(screen.getAllByText(/versão 2026-01/)).toHaveLength(3)
  })

  it('navigates an already accepted incomplete organization to Foundation', async () => {
    setClerkState({ orgId: 'org_ready', orgName: 'Escola Pronta', role: 'org:admin' })
    mockState.member = { data: adminMember, isLoading: false, isError: false, isSuccess: true }
    mockState.legal = {
      data: { ...legalStatus, accepted: true, requires_acceptance: false },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    }

    renderWithProviders(
      <MemoryRouter initialEntries={[{ pathname: '/create-org', state: { from: 'https://evil.example/' } }]}>
        <Routes>
          <Route path="/create-org" element={<CreateOrgPage />} />
          <Route path="/foundation" element={<div data-testid="foundation-route">Foundation</div>} />
          <Route path="/dashboard" element={<div data-testid="dashboard-route">Dashboard</div>} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByTestId('foundation-route')).toBeInTheDocument())
  })

  it('explains the administrator boundary to a non-administrator and offers recovery actions', async () => {
    setClerkState({ orgId: 'org_member', orgName: 'Escola Membro', role: 'org:member' })
    mockState.member = { data: teacherMember, isLoading: false, isError: false, isSuccess: true, refetch: vi.fn() }
    mockState.legal = { data: legalStatus, isLoading: false, isError: false, refetch: vi.fn() }

    renderWithRouter(<CreateOrgPage />)

    expect(screen.getByRole('alert')).toHaveTextContent('Um administrador da organização deve aceitar')
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.getByTestId('organization-switcher')).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Atualizar' }))
    expect(mockState.legal.refetch).toHaveBeenCalled()
  })

  it('shows a retry action when legal status fails', async () => {
    const user = userEvent.setup()
    setClerkState({ orgId: 'org_error', orgName: 'Escola Erro', role: 'org:admin' })
    mockState.member = { data: adminMember, isLoading: false, isError: false, isSuccess: true }
    mockState.legal = { data: null, isLoading: false, isError: true, refetch: vi.fn() }

    renderWithRouter(<CreateOrgPage />)

    await user.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    expect(mockState.legal.refetch).toHaveBeenCalledTimes(1)
  })
})
