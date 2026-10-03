import { describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
import { beforeEach } from 'vitest'
import { renderWithRouter } from './testUtils'
import Members from '../pages/Members'

const { useMembersMock } = vi.hoisted(() => ({ useMembersMock: vi.fn() }))

vi.mock('../features/members/data', () => {
  const mutation = () => ({
    error: null,
    isPending: false,
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
  })

  return {
    useMembers: () => useMembersMock(),
    useTeachers: () => ({ data: [] }),
    useCreateMember: mutation,
    useUpdateMember: mutation,
    useRemoveMember: mutation,
    useResendMemberInvitation: mutation,
    useRestoreMember: mutation,
    useRetryMemberSync: mutation,
  }
})

vi.mock('../features/catalog/data', () => ({
  useSubjects: () => ({ data: [] }),
}))

describe('Members', () => {
  beforeEach(() => {
    useMembersMock.mockReturnValue({
      data: { items: [] },
      error: null,
      isError: false,
      isLoading: false,
      refetch: vi.fn(),
    })
  })

  it('uses the shared page spacing', () => {
    const { container } = renderWithRouter(<Members />)

    expect(container.firstChild).toHaveClass('p-4')
  })

  it('exposes the member form controls through their visible labels', async () => {
    renderWithRouter(<Members />)

    fireEvent.click(screen.getByRole('button', { name: /adicionar membro/i }))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('textbox', { name: 'Nome' })).toBeEnabled()
    expect(within(dialog).getByRole('textbox', { name: 'Email' })).toBeEnabled()
    expect(within(dialog).getByRole('combobox', { name: 'Tipo de membro' })).toBeEnabled()
    expect(within(dialog).getByRole('combobox', { name: 'Acesso do professor' })).toBeEnabled()
  })

  it('keeps action descriptions hoverable when the icon buttons are disabled', () => {
    useMembersMock.mockReturnValue({
      data: {
        items: [{
          id: 7,
          organization_display_name: 'Ana Silva',
          email: 'ana@example.test',
          capabilities: ['teacher'],
          teacher_access_mode: 'platform',
          subject_ids: [],
          access_status: 'active',
          lifecycle_status: 'active',
          can_resend_invitation: false,
          can_retry_sync: false,
          can_restore: false,
          lock_version: 1,
        }],
      },
      error: null,
      isError: false,
      isLoading: false,
      refetch: vi.fn(),
    })

    renderWithRouter(<Members />)

    for (const description of ['Reenviar convite', 'Tentar sincronização novamente', 'Restaurar membro']) {
      expect(screen.getByTitle(description)).toBeVisible()
    }
  })

  it('maps provider error categories to local neutral copy', () => {
    useMembersMock.mockReturnValue({
      data: {
        items: [{
          id: 8,
          organization_display_name: 'Ana Silva',
          email: 'ana@example.test',
          capabilities: ['teacher'],
          teacher_access_mode: 'platform',
          subject_ids: [],
          access_status: 'sync_error',
          lifecycle_status: 'active',
          provider_state: 'unconfirmed',
          access_error_category: 'provider_role_mismatch',
          access_error_safe_message: 'Clerk role does not match the expected local access.',
          can_resend_invitation: false,
          can_retry_sync: true,
          can_restore: false,
          lock_version: 1,
        }],
      },
      error: null,
      isError: false,
      isLoading: false,
      refetch: vi.fn(),
    })

    renderWithRouter(<Members />)

    expect(screen.getByText('Os dados de acesso precisam de ser confirmados.')).toBeInTheDocument()
    expect(screen.queryByText('Clerk role does not match the expected local access.')).toBeNull()
    expect(screen.queryByText('Fornecedor por confirmar')).toBeNull()
  })
})
