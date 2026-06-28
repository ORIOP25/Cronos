import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Schedules from '../pages/Schedules'

const mocks = vi.hoisted(() => ({
  status: null,
  currentDraft: null,
  generate: vi.fn(),
  approve: vi.fn(),
}))

vi.mock('../hooks/useRole', () => ({
  useRole: () => ({ isAdmin: true, isTeacher: false }),
}))

vi.mock('../hooks/useSchoolData', () => ({
  useSchedulerStatus: () => ({ data: mocks.status, refetch: vi.fn() }),
  useCurrentDraftSummary: () => ({ data: mocks.currentDraft, refetch: vi.fn() }),
  useApproveDraft: () => ({ mutateAsync: mocks.approve, isPending: false }),
  useRejectDraft: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useGenerateSchedule: () => ({ mutateAsync: mocks.generate, isPending: false }),
  useScheduleTaskStatus: () => ({ data: null }),
  useCancelScheduleTask: () => ({ mutate: vi.fn(), isPending: false }),
  useClasses: () => ({ data: [] }),
  useTeachers: () => ({ data: [] }),
  useWeekSchedule: () => ({ data: [], isFetching: false, isError: false }),
  useClassDetails: () => ({ data: null }),
  useTimeslots: () => ({ data: [] }),
}))

vi.mock('../components/schedules/DraftPanel', () => ({
  default: ({ draft, onApprove }) => (
    <div>
      Rever rascunho {draft.draft_id}
      <button type="button" onClick={() => onApprove(draft.draft_id)}>Aprovar teste</button>
    </div>
  ),
}))
vi.mock('../components/WeekGrid', () => ({ default: () => <div>Week grid</div> }))
vi.mock('../components/LessonLogModal', () => ({ default: () => null }))
vi.mock('../components/schedules/KPISidebar', () => ({ default: () => null }))
vi.mock('../components/schedules/GenerationStatusPanel', () => ({ default: () => null }))

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Schedules />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('Schedules scheduler flow', () => {
  afterEach(cleanup)

  beforeEach(() => {
    localStorage.clear()
    mocks.generate.mockReset()
    mocks.approve.mockReset()
    mocks.currentDraft = null
  })

  it('makes pending draft review primary and hides ordinary generation', () => {
    mocks.status = {
      pending_draft_id: 77,
      primary_action: 'REVIEW_PENDING_DRAFT',
      can_generate_new_draft: false,
      can_regenerate_with_confirmation: true,
      blocked_reason: null,
    }
    mocks.currentDraft = { draft_id: 77 }

    renderPage()

    expect(screen.getByText('Rever rascunho 77')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Gerar novamente' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Gerar Horário' })).not.toBeInTheDocument()
  })

  it('replaces a pending draft only after explicit confirmation', async () => {
    mocks.status = {
      pending_draft_id: 77,
      primary_action: 'REVIEW_PENDING_DRAFT',
      can_generate_new_draft: false,
      can_regenerate_with_confirmation: true,
      blocked_reason: null,
    }
    mocks.currentDraft = { draft_id: 77 }
    mocks.generate.mockResolvedValue({ job_id: 91 })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Gerar novamente' }))

    await waitFor(() => {
      expect(confirmSpy).toHaveBeenCalledOnce()
      expect(mocks.generate).toHaveBeenCalledWith({ replacePendingDraft: true })
    })
    confirmSpy.mockRestore()
  })

  it('shows the only generation action when the status allows it', () => {
    mocks.status = {
      pending_draft_id: null,
      primary_action: 'GENERATE_SCHEDULE',
      can_generate_new_draft: true,
      can_regenerate_with_confirmation: false,
      blocked_reason: null,
    }

    renderPage()

    expect(screen.getByRole('button', { name: 'Gerar Horário' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Gerar novamente' })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: /modo|estratégia/i })).not.toBeInTheDocument()
  })

  it('shows the unavailable reason without a generation command', () => {
    mocks.status = {
      pending_draft_id: null,
      primary_action: 'GENERATION_UNAVAILABLE',
      can_generate_new_draft: false,
      can_regenerate_with_confirmation: false,
      blocked_reason: 'No schedule generation needed.',
    }

    renderPage()

    expect(screen.getByText('No schedule generation needed.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Gerar Horário' })).not.toBeInTheDocument()
  })

  it('explains how to recover when approval finds a stale draft', async () => {
    mocks.status = {
      pending_draft_id: 77,
      primary_action: 'REVIEW_PENDING_DRAFT',
      can_generate_new_draft: false,
      can_regenerate_with_confirmation: true,
      blocked_reason: null,
    }
    mocks.currentDraft = { draft_id: 77 }
    mocks.approve.mockRejectedValue({
      response: { data: { detail: { draft_state: 'STALE' } } },
    })

    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Aprovar teste' }))

    expect(await screen.findByText(/This draft is no longer current/)).toHaveTextContent(
      'Regenerate the draft to continue.'
    )
  })
})
