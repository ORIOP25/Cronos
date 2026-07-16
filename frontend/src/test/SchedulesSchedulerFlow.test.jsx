import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Schedules from '../pages/Schedules'
import { renderWithRouter } from './testUtils'

const mocks = vi.hoisted(() => ({
  status: null,
  currentDraft: null,
  generate: vi.fn(),
  approve: vi.fn(),
}))

vi.mock('../hooks/useRole', () => ({
  useRole: () => ({ isAdmin: true, isTeacher: false }),
}))

vi.mock('../features/scheduling/data', () => ({
  useSchedulerStatus: () => ({ data: mocks.status, refetch: vi.fn() }),
  useCurrentDraftSummary: () => ({ data: mocks.currentDraft, refetch: vi.fn() }),
  useApproveDraft: () => ({ mutateAsync: mocks.approve, isPending: false }),
  useRejectDraft: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useGenerateSchedule: () => ({ mutateAsync: mocks.generate, isPending: false }),
  useScheduleTaskStatus: () => ({ data: null }),
  useCancelScheduleTask: () => ({ mutate: vi.fn(), isPending: false }),
  useWeekSchedule: () => ({ data: [], isFetching: false, isError: false }),
}))

vi.mock('../features/members/data', () => ({
  useCurrentMember: () => ({ data: { teacher_id: null } }),
  useTeachers: () => ({ data: [] }),
}))

vi.mock('../features/catalog/data', () => ({
  useClasses: () => ({ data: [] }),
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
  return renderWithRouter(<Schedules />)
}

describe('Schedules scheduler flow', () => {
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

    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Gerar novamente' }))
    expect(await screen.findByText(/substituir o rascunho pendente/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /confirmar gera/i }))

    await waitFor(() => {
      expect(mocks.generate).toHaveBeenCalledWith({ replacePendingDraft: true })
    })
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

  it('hides the generation command without showing an unavailable reason', () => {
    mocks.status = {
      pending_draft_id: null,
      primary_action: 'GENERATION_UNAVAILABLE',
      can_generate_new_draft: false,
      can_regenerate_with_confirmation: false,
      blocked_reason: null,
    }

    renderPage()

    expect(screen.queryByText('No schedule generation needed.')).not.toBeInTheDocument()
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
