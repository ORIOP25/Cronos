import { describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'
import { renderWithProviders } from './testUtils'
import Members from '../pages/Members'

vi.mock('../features/members/data', () => {
  const mutation = () => ({
    error: null,
    isPending: false,
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
  })

  return {
    useMembers: () => ({
      data: { items: [] },
      error: null,
      isError: false,
      isLoading: false,
      refetch: vi.fn(),
    }),
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
  it('exposes the member form controls through their visible labels', async () => {
    renderWithProviders(<Members />)

    fireEvent.click(screen.getByRole('button', { name: /adicionar membro/i }))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('textbox', { name: 'Nome' })).toBeEnabled()
    expect(within(dialog).getByRole('textbox', { name: 'Email' })).toBeEnabled()
    expect(within(dialog).getByRole('combobox', { name: 'Tipo de membro' })).toBeEnabled()
    expect(within(dialog).getByRole('combobox', { name: 'Acesso do professor' })).toBeEnabled()
  })
})
