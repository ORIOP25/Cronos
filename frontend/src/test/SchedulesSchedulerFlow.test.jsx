import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Schedules from '../pages/Schedules'
import { renderWithRouter } from './testUtils'
import { writeExpiringValue } from '../utils/expiringStorage'

const mocks = vi.hoisted(() => ({
  status: null,
  currentDraft: null,
  jobData: null,
  classes: [],
  generate: vi.fn(),
  approve: vi.fn(),
  schedulerStatusRefetch: vi.fn(),
  currentDraftRefetch: vi.fn(),
  weekRefetch: vi.fn(),
  prevalidation: { data: null, isFetching: false, isError: false, refetch: vi.fn() },
}))

vi.mock('../features/readiness/data', () => ({
  usePrevalidation: () => mocks.prevalidation,
  invalidatePreparationQueries: vi.fn(),
}))

vi.mock('../hooks/useRole', () => ({
  useRole: () => ({ isAdmin: true, isTeacher: false }),
}))

vi.mock('../features/scheduling/data', () => ({
  useSchedulerStatus: () => ({ data: mocks.status, refetch: mocks.schedulerStatusRefetch }),
  useCurrentDraftSummary: () => ({ data: mocks.currentDraft, refetch: mocks.currentDraftRefetch }),
  useApproveDraft: () => ({ mutateAsync: mocks.approve, isPending: false }),
  useRejectDraft: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useGenerateSchedule: () => ({ mutateAsync: mocks.generate, isPending: false }),
  useScheduleTaskStatus: () => ({ data: mocks.jobData }),
  useCancelScheduleTask: () => ({ mutate: vi.fn(), isPending: false }),
  useWeekSchedule: () => ({
    data: [],
    isFetching: false,
    isError: false,
    refetch: mocks.weekRefetch,
  }),
}))

vi.mock('../features/members/data', () => ({
  useCurrentMember: () => ({ data: { teacher_id: null } }),
  useTeachers: () => ({ data: [] }),
}))

vi.mock('../features/catalog/data', () => ({
  useClasses: () => ({ data: mocks.classes }),
  useClassDetails: () => ({ data: null }),
  useTimeslots: () => ({ data: [] }),
  useWeekGridVersions: () => ({ data: null }),
}))

vi.mock('../components/schedules/DraftPanel', () => ({
  default: ({ draft, onApprove }) => (
    <div>
      Rever proposta {draft.proposal_id}
      <button type="button" onClick={() => onApprove(draft.proposal_id)}>Aprovar teste</button>
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

function proposalStatus(overrides = {}) {
  return {
    configured: true,
    school_year: { preferred_end_date: '2027-06-15' },
    publication_state: 'UNPUBLISHED',
    active_version_id: null,
    revisions: { input: 0, planning: 0, last_completed_planning: null, last_successful_generation_at: null },
    eligibility: { can_generate: true, reasons: ['FIRST_GENERATION'], blocker: null },
    default_strategy: 'COMPLETE_GENERATION',
    active_job: null,
    pending_proposal: { proposal_id: 77, can_approve: true, is_stale: false, metrics: {} },
    ...overrides,
  }
}

describe('Schedules scheduler flow', () => {
  beforeEach(() => {
    localStorage.clear()
    mocks.generate.mockReset()
    mocks.approve.mockReset()
    mocks.schedulerStatusRefetch.mockReset()
    mocks.currentDraftRefetch.mockReset()
    mocks.weekRefetch.mockReset()
    mocks.currentDraft = null
    mocks.jobData = null
    mocks.classes = []
    mocks.prevalidation = {
      data: { status: 'READY', fingerprint: null, issues: [] },
      isFetching: false,
      isError: false,
      refetch: vi.fn(),
    }
  })

  it('shows the pending proposal and an update action that requires confirmation', async () => {
    mocks.status = proposalStatus({
      publication_state: 'PUBLISHED',
      active_version_id: 5,
      default_strategy: 'ADAPTIVE_RECOVERY',
    })
    mocks.currentDraft = { proposal_id: 77 }
    mocks.generate.mockResolvedValue({ job: { id: 91 } })

    renderPage()

    expect(screen.getByText('Rever proposta 77')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Atualizar horário' }))
    expect(await screen.findByText(/substituir a proposta pendente/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /confirmar gera/i }))

    await waitFor(() => {
      expect(mocks.generate).toHaveBeenCalledWith({
        idempotencyKey: expect.any(String),
        expectedInputRevision: 0,
      })
    })
  })

  it('shows the first generation action when the server allows it', () => {
    mocks.status = proposalStatus({ pending_proposal: null })

    renderPage()

    expect(screen.getByRole('button', { name: 'Gerar horário' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Atualizar horário' })).not.toBeInTheDocument()
  })

  it('explains the missing preferred end date before generation', () => {
    mocks.status = proposalStatus({
      school_year: { preferred_end_date: null },
      pending_proposal: null,
    })

    renderPage()

    expect(screen.queryByRole('button', { name: 'Gerar horário' })).not.toBeInTheDocument()
    expect(screen.getByText(/Defina a data preferencial de fim/i)).toBeInTheDocument()
    expect(mocks.generate).not.toHaveBeenCalled()
  })

  it('explains that there is nothing to generate when there is no reason', () => {
    mocks.status = proposalStatus({
      eligibility: { can_generate: false, reasons: [], blocker: null },
      pending_proposal: null,
    })

    renderPage()

    expect(screen.queryByRole('button', { name: 'Gerar horário' })).not.toBeInTheDocument()
    expect(screen.getByText(/Não existem alterações por aplicar ao horário/)).toBeInTheDocument()
  })

  it('refreshes the state when a generation finishes without a selected view', async () => {
    writeExpiringValue(localStorage, 'hz-schedule-active-job-org-1', '91')
    mocks.status = proposalStatus({ pending_proposal: null })
    mocks.jobData = { status: 'SUCCEEDED' }

    renderPage()

    await waitFor(() => {
      expect(mocks.schedulerStatusRefetch).toHaveBeenCalledOnce()
      expect(mocks.currentDraftRefetch).toHaveBeenCalledOnce()
    })
    expect(mocks.weekRefetch).not.toHaveBeenCalled()
  })

  it('explains how to recover when approval finds a stale proposal', async () => {
    mocks.status = proposalStatus()
    mocks.currentDraft = { proposal_id: 77 }
    mocks.approve.mockRejectedValue({
      response: { data: { detail: { code: 'proposal_stale' } } },
    })

    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Aprovar teste' }))

    expect(await screen.findByText(/Existem alterações mais recentes/)).toHaveTextContent(
      'Gere uma nova proposta para continuar.'
    )
  })

  it('blocks generation and shows the shortcut before it starts', () => {
    mocks.status = proposalStatus({ pending_proposal: null })
    mocks.prevalidation = {
      data: {
        status: 'BLOCKED',
        issues: [{
          code: 'NO_ELIGIBLE_ROOM',
          severity: 'BLOCKER',
          message: 'TDESP 10 / Treino Desportivo (27 alunos) sem sala compatível.',
          route: '/rooms',
        }],
      },
      isFetching: false,
      isError: false,
      refetch: vi.fn(),
    }

    renderPage()

    expect(screen.getByRole('button', { name: 'Gerar horário' })).toBeDisabled()
    expect(screen.getByText(/Geração bloqueada antes de começar/)).toBeInTheDocument()
    expect(screen.getByText(/TDESP 10 \/ Treino Desportivo/).closest('a')).toHaveAttribute('href', '/rooms')
  })

  it('keeps generation available with warnings and shows the shortcut', () => {
    mocks.status = proposalStatus({ pending_proposal: null })
    mocks.prevalidation = {
      data: {
        status: 'READY_WITH_WARNINGS',
        issues: [{
          code: 'PENDING_DRAFT',
          severity: 'WARNING',
          message: 'Existe um rascunho pendente.',
          route: '/schedules',
        }],
      },
      isFetching: false,
      isError: false,
      refetch: vi.fn(),
    }

    renderPage()

    expect(screen.getByRole('button', { name: 'Gerar horário' })).toBeEnabled()
    expect(screen.getByText(/Avisos antes de gerar/)).toBeInTheDocument()
  })

  it('offers a retry when the preparation check fails', () => {
    mocks.status = proposalStatus({ pending_proposal: null })
    mocks.prevalidation = { data: null, isFetching: false, isError: true, refetch: vi.fn() }

    renderPage()

    expect(screen.getByRole('button', { name: 'Gerar horário' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Repetir verificação' }))
    expect(mocks.prevalidation.refetch).toHaveBeenCalled()
  })

  it('explains a refused generation with the room diagnosis and a shortcut', async () => {
    mocks.status = proposalStatus({ pending_proposal: null })
    mocks.generate.mockRejectedValue({
      response: {
        status: 422,
        data: {
          detail: {
            code: 'NO_ELIGIBLE_ROOM',
            reference: 'ROOMREF12345',
            context: {
              room_issues: [{
                class_name: 'TDESP 10',
                subject_name: 'Treino Desportivo',
                required_room_type: 'gym',
                required_capacity: 27,
                max_available_capacity: 26,
                reason: 'INSUFFICIENT_CAPACITY',
              }],
            },
          },
        },
      },
    })

    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Gerar horário' }))

    expect(await screen.findByText(/27 alunos/)).toBeInTheDocument()
    expect(screen.getByText('Abrir Salas')).toHaveAttribute('href', '/rooms')
    expect(screen.getByText('ROOMREF12345')).toBeInTheDocument()
  })

  it('refreshes preparation and scheduler state when the data changed meanwhile', async () => {
    mocks.status = proposalStatus({ pending_proposal: null })
    mocks.generate.mockRejectedValue({
      response: { data: { detail: { code: 'scheduler_state_changed' } } },
    })

    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Gerar horário' }))

    await waitFor(() => {
      expect(mocks.schedulerStatusRefetch).toHaveBeenCalled()
      expect(mocks.prevalidation.refetch).toHaveBeenCalled()
    })
  })

  it('drops a persisted class that is not part of the current organization', async () => {
    writeExpiringValue(localStorage, 'hz-schedule-view-org-1', {
      viewMode: 'class',
      selectedClassId: '33',
      selectedTeacherId: '',
      weekStart: '2026-09-21',
    })
    mocks.status = proposalStatus({ pending_proposal: null })
    mocks.classes = [1, 2, 3, 4, 5, 6].map((id) => ({ id, name: `Turma ${id}` }))

    renderPage()

    const select = await screen.findByLabelText('Turma')
    await waitFor(() => expect(select).toHaveValue(''))
  })
})
