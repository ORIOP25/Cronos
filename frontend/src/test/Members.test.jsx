import { describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { beforeEach } from 'vitest'
import { renderWithRouter } from './testUtils'
import Members from '../pages/Members'

const { useMembersMock, resendMock, updateMock, removeMock } = vi.hoisted(() => ({ useMembersMock: vi.fn(), resendMock: vi.fn(), updateMock: vi.fn(), removeMock: vi.fn() }))

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
    useUpdateMember: () => ({ mutateAsync: updateMock, isPending: false }),
    useRemoveMember: () => ({ mutateAsync: removeMock, isPending: false }),
    useResendMemberInvitation: () => resendMock(),
    useRestoreMember: mutation,
    useRetryMemberSync: mutation,
  }
})

vi.mock('../features/catalog/data', () => ({
  useSubjects: () => ({ data: [] }),
}))

vi.mock('../components/TeacherAvailabilityModal', () => ({
  default: ({ teacher, onClose }) => <div role="dialog">Disponibilidade — {teacher.name} (professor {teacher.id})<button onClick={onClose}>Fechar disponibilidade</button></div>,
}))

describe('Members', () => {
  it('opens administrative availability from the member editor, independently of access', async () => {
    useMembersMock.mockReturnValue({ data: { items: [{ id: 684, teacher_id: 657,
      organization_display_name: 'Professor QA', capabilities: ['teacher'],
      access_status: 'none', lifecycle_status: 'active', teacher_access_mode: 'scheduler_only',
    }] }, isLoading: false, isError: false })
    renderWithRouter(<Members />)
    expect(screen.queryByRole('button', { name: 'Editar disponibilidade' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Editar membro' }))
    await screen.findByRole('dialog')
    fireEvent.click(screen.getByRole('button', { name: 'Editar disponibilidade' }))
    expect(await screen.findByText('Disponibilidade — Professor QA (professor 657)')).toBeInTheDocument()
  })

  it('explains an unknown teacher link instead of opening an unidentified grid', () => {
    renderWithRouter(<Members />, { initialEntries: ['/members?teacher_id=684&panel=availability'] })
    expect(screen.getByRole('status')).toHaveTextContent('Professor não encontrado')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  beforeEach(() => {
    resendMock.mockReturnValue({ error: null, isPending: false, mutate: vi.fn() })
    updateMock.mockReset().mockResolvedValue({})
    removeMock.mockReset().mockResolvedValue({})
    useMembersMock.mockReturnValue({
      data: { items: [] },
      error: null,
      isError: false,
      isLoading: false,
      refetch: vi.fn(),
    })
  })

  it('shows access action failures inside the member editor', async () => {
    const member = { id: 4, organization_display_name: 'Ana', email: 'ana@example.test',
      capabilities: ['teacher'], access_status: 'pending_invite', lifecycle_status: 'active',
      actions: { can_edit: true, can_resend_invite: true } }
    useMembersMock.mockReturnValue({ data: { items: [member] }, isLoading: false })
    resendMock.mockReturnValue({ error: { response: { status: 409, data: { detail: { code: 'member_sync_error' } } } }, isPending: false, mutate: vi.fn() })
    renderWithRouter(<Members />)
    fireEvent.click(screen.getByRole('button', { name: 'Editar membro' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('alert')).toHaveTextContent('O acesso ainda está a ser confirmado. Tente novamente dentro de instantes.')
    expect(within(dialog).getByRole('button', { name: 'Reenviar convite' })).toBeEnabled()
  })

  it('uses the new version after resending without losing unsaved edits', async () => {
    const member = { id: 4, organization_display_name: 'Ana', email: 'ana@example.test', lock_version: 1,
      capabilities: ['teacher'], access_status: 'pending_invite', lifecycle_status: 'active',
      actions: { can_edit: true, can_resend_invite: true } }
    useMembersMock.mockReturnValue({ data: { items: [member] }, isLoading: false })
    resendMock.mockReturnValue({ error: null, isPending: false, mutate: (_id, options) => options.onSuccess({ ...member, lock_version: 2 }) })
    renderWithRouter(<Members />)
    fireEvent.click(screen.getByRole('button', { name: 'Editar membro' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Nome'), { target: { value: 'Ana editada' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reenviar convite' }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(updateMock).toHaveBeenCalledWith(expect.objectContaining({ organization_display_name: 'Ana editada', lock_version: 2 })))
  })

  it('keeps the original edit version when another change preceded the access action', async () => {
    const member = { id: 4, organization_display_name: 'Ana', email: 'ana@example.test', lock_version: 1,
      capabilities: ['teacher'], access_status: 'pending_invite', lifecycle_status: 'active',
      actions: { can_edit: true, can_resend_invite: true } }
    useMembersMock.mockReturnValue({ data: { items: [member] }, isLoading: false })
    resendMock.mockReturnValue({ error: null, isPending: false, mutate: (_id, options) => options.onSuccess({ ...member, organization_display_name: 'Beatriz', lock_version: 3 }) })
    renderWithRouter(<Members />)
    fireEvent.click(screen.getByRole('button', { name: 'Editar membro' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reenviar convite' }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(updateMock).toHaveBeenCalledWith(expect.objectContaining({ lock_version: 1 })))
  })

  it('returns from availability with the unsaved member draft intact', async () => {
    const member = { id: 4, teacher_id: 7, organization_display_name: 'Ana', email: 'ana@example.test', lock_version: 1,
      capabilities: ['teacher'], access_status: 'none', lifecycle_status: 'active', actions: { can_edit: true } }
    useMembersMock.mockReturnValue({ data: { items: [member] }, isLoading: false })
    renderWithRouter(<Members />)
    fireEvent.click(screen.getByRole('button', { name: 'Editar membro' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Nome'), { target: { value: 'Ana editada' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Editar disponibilidade' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Fechar disponibilidade' }))
    expect(await screen.findByLabelText('Nome')).toHaveValue('Ana editada')
  })

  it('closes the member editor after confirmed removal', async () => {
    const member = { id: 4, organization_display_name: 'Ana', email: 'ana@example.test', lock_version: 1,
      capabilities: ['teacher'], access_status: 'none', lifecycle_status: 'active', remove_effect: 'hard_delete',
      actions: { can_edit: true, can_remove: true } }
    useMembersMock.mockReturnValue({ data: { items: [member] }, isLoading: false })
    renderWithRouter(<Members />)
    fireEvent.click(screen.getByRole('button', { name: 'Editar membro' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Remover membro' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Remover', exact: true }))
    await waitFor(() => expect(removeMock).toHaveBeenCalledWith(4))
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Editar membro' })).not.toBeInTheDocument())
  })

  it('labels the archive filter and lets its visible label toggle it', () => {
    renderWithRouter(<Members />)
    const filter = screen.getByRole('checkbox', { name: 'Mostrar arquivados' })
    expect(filter).not.toBeChecked()
    fireEvent.click(screen.getByText('Mostrar arquivados', { exact: true }))
    expect(filter).toBeChecked()
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

  it('keeps unavailable access actions out of the team table', () => {
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

    for (const description of ['Reenviar convite', 'Tentar confirmar o acesso novamente', 'Restaurar membro']) {
      expect(screen.queryByTitle(description)).not.toBeInTheDocument()
    }
    expect(screen.getAllByRole('button', { name: 'Editar membro' })).toHaveLength(1)
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

  it('shows the rule badges next to the teaching label', () => {
    useMembersMock.mockReturnValue({
      data: {
        items: [{
          id: 9,
          teacher_id: 7,
          organization_display_name: 'Ana Silva',
          email: 'ana@example.test',
          capabilities: ['teacher'],
          teacher_access_mode: 'platform',
          subject_ids: [],
          access_status: 'active',
          lifecycle_status: 'active',
          lock_version: 1,
          teacher_presence: { lunch_required: false, minimum_hours: 3, max_gap_hours: 1 },
        }],
      },
      error: null,
      isError: false,
      isLoading: false,
      refetch: vi.fn(),
    })

    renderWithRouter(<Members />)

    expect(screen.getByText('Professor')).toBeInTheDocument()
    expect(screen.getByText('Sem almoço')).toBeInTheDocument()
    expect(screen.getByText('Mín. 3h · furo 1h')).toBeInTheDocument()
  })

  it('hides the rule badges for the default rule', () => {
    useMembersMock.mockReturnValue({
      data: {
        items: [{
          id: 10,
          teacher_id: 8,
          organization_display_name: 'Bruno Costa',
          email: 'bruno@example.test',
          capabilities: ['teacher'],
          teacher_access_mode: 'platform',
          subject_ids: [],
          access_status: 'active',
          lifecycle_status: 'active',
          lock_version: 1,
          teacher_presence: { lunch_required: true, minimum_hours: null, max_gap_hours: null },
        }],
      },
      error: null,
      isError: false,
      isLoading: false,
      refetch: vi.fn(),
    })

    renderWithRouter(<Members />)

    expect(screen.queryByText('Sem almoço')).not.toBeInTheDocument()
    expect(screen.queryByText(/Mín\./)).not.toBeInTheDocument()
  })
})
