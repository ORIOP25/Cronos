import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'react-hot-toast'
import { MemoryRouter } from 'react-router-dom'
import Schedules from '../pages/Schedules'
import { renderWithRouter } from './testUtils'
import { writeExpiringValue } from '../utils/expiringStorage'
import { resetClerkState, setClerkState } from './setup'

const mocks = vi.hoisted(() => ({
  status: null,
  currentDraft: null,
  jobData: null,
  classes: [],
  generate: vi.fn(),
  approve: vi.fn(),
  reject: vi.fn(),
  cancel: vi.fn(),
  prevalidationOptions: vi.fn(),
  taskStatus: vi.fn(),
  schedulerStatusRefetch: vi.fn(),
  currentDraftRefetch: vi.fn(),
  weekRefetch: vi.fn(),
  weekRequest: vi.fn(),
  gridProps: vi.fn(),
  prevalidation: { data: null, isFetching: false, isError: false, refetch: vi.fn() },
}))

vi.mock('../features/readiness/data', () => ({
  usePrevalidation: (options) => { mocks.prevalidationOptions(options); return mocks.prevalidation },
  invalidatePreparationQueries: vi.fn(),
}))

vi.mock('../hooks/useRole', () => ({
  useRole: () => ({ isAdmin: true, isTeacher: false }),
}))

vi.mock('../features/scheduling/data', () => ({
  useSchedulerStatus: () => ({ data: mocks.status, refetch: mocks.schedulerStatusRefetch }),
  useCurrentDraftSummary: () => ({ data: mocks.currentDraft, refetch: mocks.currentDraftRefetch }),
  useApproveDraft: () => ({ mutateAsync: mocks.approve, isPending: false }),
  useRejectDraft: () => ({ mutateAsync: mocks.reject, isPending: false }),
  useGenerateSchedule: () => ({ mutateAsync: mocks.generate, isPending: false }),
  useScheduleTaskStatus: (jobId) => { mocks.taskStatus(jobId); return { data: mocks.jobData } },
  useCancelScheduleTask: () => ({ mutate: mocks.cancel, isPending: false }),
  useWeekSchedule: (...args) => {
    mocks.weekRequest(...args)
    return { data: [], isFetching: false, isError: false, refetch: mocks.weekRefetch }
  },
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
  default: ({ draft, onApprove, onReject }) => (
    <div>
      Rever proposta {draft.proposal_id}
      <button type="button" onClick={() => onApprove(draft.proposal_id)}>Aprovar teste</button>
      <button type="button" onClick={() => onReject(draft.proposal_id)}>Rejeitar teste</button>
    </div>
  ),
}))
vi.mock('../components/WeekGrid', () => ({
  default: (props) => { mocks.gridProps(props); return <div>Week grid</div> },
}))
vi.mock('../components/LessonLogModal', () => ({ default: () => null }))
vi.mock('../components/schedules/KPISidebar', () => ({ default: () => null }))
vi.mock('../components/schedules/GenerationStatusPanel', () => ({ default: () => null }))

function renderPage() {
  return renderWithRouter(<Schedules />)
}

const PROPOSAL_BANNER = 'Está a ver a proposta pendente. Nada muda no horário publicado até a aprovar.'

function renderClassGrid() {
  return renderWithRouter(<Schedules initialClassId="5" />)
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
  afterEach(() => {
    resetClerkState()
    vi.restoreAllMocks()
  })
  beforeEach(() => {
    localStorage.clear()
    mocks.generate.mockReset()
    mocks.approve.mockReset()
    mocks.reject.mockReset()
    mocks.cancel.mockReset()
    mocks.prevalidationOptions.mockReset()
    mocks.taskStatus.mockReset()
    mocks.schedulerStatusRefetch.mockReset()
    mocks.currentDraftRefetch.mockReset()
    mocks.weekRefetch.mockReset()
    mocks.weekRequest.mockReset()
    mocks.gridProps.mockReset()
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

  it('checks teacher presence before updating a published timetable', () => {
    mocks.status = proposalStatus({ publication_state: 'PUBLISHED', active_version_id: 5, default_strategy: 'ADAPTIVE_RECOVERY', pending_proposal: null })
    mocks.prevalidation.data = { status: 'BLOCKED', issues: [{ code: 'TEACHER_PRESENCE_IMPOSSIBLE', message: 'Íris precisa de 12 horas.', route: '/members' }] }
    renderPage()
    expect(mocks.prevalidationOptions).toHaveBeenLastCalledWith({ enabled: true, strategy: 'ADAPTIVE_REPAIR' })
    expect(screen.getByRole('button', { name: 'Atualizar horário' })).toBeDisabled()
    expect(screen.getByRole('link', { name: /Íris precisa/i })).toHaveAttribute('href', '/members')
  })

  it('keeps a persisted cancellation request visible while the worker stops', () => {
    mocks.status = proposalStatus({ active_job: { id: 9 }, pending_proposal: null })
    mocks.jobData = { id: 9, status: 'RUNNING', cancellation_requested: true }
    renderPage()
    expect(screen.getByRole('button', { name: /A cancelar…/ })).toBeDisabled()
  })

  it('previews the pending proposal in the week grid when the proposal toggle is pressed', () => {
    mocks.status = proposalStatus({ publication_state: 'PUBLISHED', active_version_id: 5, default_strategy: 'ADAPTIVE_RECOVERY' })

    renderClassGrid()

    expect(screen.getByRole('button', { name: 'Horário publicado' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByText(PROPOSAL_BANNER)).not.toBeInTheDocument()
    expect(mocks.weekRequest).toHaveBeenLastCalledWith(5, null, expect.any(String), null)

    fireEvent.click(screen.getByRole('button', { name: 'Proposta pendente' }))

    expect(screen.getByRole('button', { name: 'Proposta pendente' })).toHaveAttribute('aria-pressed', 'true')
    expect(mocks.weekRequest).toHaveBeenLastCalledWith(5, null, expect.any(String), 77)
    expect(screen.getByText(PROPOSAL_BANNER)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Horário publicado' }))

    expect(mocks.weekRequest).toHaveBeenLastCalledWith(5, null, expect.any(String), null)
    expect(screen.queryByText(PROPOSAL_BANNER)).not.toBeInTheDocument()
  })

  it('does not offer the proposal toggle without a pending proposal', () => {
    mocks.status = proposalStatus({ pending_proposal: null })

    renderClassGrid()

    expect(screen.queryByRole('button', { name: 'Horário publicado' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Proposta pendente' })).not.toBeInTheDocument()
  })

  it.each([
    ['is_stale', { is_stale: true }],
    ['status STALE', { status: 'STALE' }],
  ])('does not offer the proposal toggle when the pending proposal is stale (%s)', (_label, staleFlag) => {
    mocks.status = proposalStatus({ pending_proposal: { proposal_id: 77, can_approve: false, metrics: {}, ...staleFlag } })

    renderClassGrid()

    expect(screen.queryByRole('button', { name: 'Horário publicado' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Proposta pendente' })).not.toBeInTheDocument()
  })

  it('keeps the grid read-only while the proposal is previewed', () => {
    mocks.status = proposalStatus({ publication_state: 'PUBLISHED', active_version_id: 5, default_strategy: 'ADAPTIVE_RECOVERY' })

    renderClassGrid()
    expect(mocks.gridProps.mock.lastCall[0]).toMatchObject({ isOperationalEnabled: true })
    expect(mocks.gridProps.mock.lastCall[0].onOpenOperationalAction).toEqual(expect.any(Function))

    fireEvent.click(screen.getByRole('button', { name: 'Proposta pendente' }))

    expect(mocks.gridProps.mock.lastCall[0]).toMatchObject({ isOperationalEnabled: false })
    expect(mocks.gridProps.mock.lastCall[0].onOpenOperationalAction).toBeUndefined()
  })

  it('returns to the published grid when the previewed proposal is no longer pending', () => {
    mocks.status = proposalStatus({ publication_state: 'PUBLISHED', active_version_id: 5, default_strategy: 'ADAPTIVE_RECOVERY' })
    const page = renderClassGrid()
    fireEvent.click(screen.getByRole('button', { name: 'Proposta pendente' }))
    expect(screen.getByText(PROPOSAL_BANNER)).toBeInTheDocument()

    mocks.status = proposalStatus({ publication_state: 'PUBLISHED', active_version_id: 6, pending_proposal: null })
    page.rerender(<MemoryRouter><Schedules initialClassId="5" /></MemoryRouter>)

    expect(screen.queryByRole('button', { name: 'Proposta pendente' })).not.toBeInTheDocument()
    expect(screen.queryByText(PROPOSAL_BANNER)).not.toBeInTheDocument()
    expect(mocks.weekRequest).toHaveBeenLastCalledWith(5, null, expect.any(String), null)
  })

  it('keeps the published grid when a newer proposal replaces the previewed one', () => {
    mocks.status = proposalStatus({ publication_state: 'PUBLISHED', active_version_id: 5, default_strategy: 'ADAPTIVE_RECOVERY' })
    const page = renderClassGrid()
    fireEvent.click(screen.getByRole('button', { name: 'Proposta pendente' }))

    mocks.status = proposalStatus({ publication_state: 'PUBLISHED', active_version_id: 5, default_strategy: 'ADAPTIVE_RECOVERY', pending_proposal: { proposal_id: 78, can_approve: true, is_stale: false, metrics: {} } })
    page.rerender(<MemoryRouter><Schedules initialClassId="5" /></MemoryRouter>)

    expect(screen.getByRole('button', { name: 'Horário publicado' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByText(PROPOSAL_BANNER)).not.toBeInTheDocument()
    expect(mocks.weekRequest).toHaveBeenLastCalledWith(5, null, expect.any(String), null)
  })

  it('keeps tracking a newly started job after asking to cancel it', async () => {
    mocks.status = proposalStatus({ pending_proposal: null })
    mocks.generate.mockResolvedValue({ job: { id: 91 } })
    const page = renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Gerar horário' }))
    fireEvent.click(await screen.findByRole('button', { name: /iniciar gera/i }))
    await waitFor(() => expect(mocks.taskStatus).toHaveBeenLastCalledWith(91))
    mocks.jobData = { id: 91, status: 'RUNNING', cancellation_requested: false }
    page.rerender(<MemoryRouter><Schedules /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar geração' }))
    expect(mocks.cancel).toHaveBeenCalledWith(91, expect.any(Object))
    expect(mocks.taskStatus).toHaveBeenLastCalledWith(91)
  })

  it('shows the teacher admission error and refreshes prevalidation', async () => {
    mocks.status = proposalStatus({ pending_proposal: null })
    mocks.generate.mockRejectedValue({ response: { status: 422, data: { detail: {
      code: 'TEACHER_PRESENCE_IMPOSSIBLE', context: { teacher_issues: [{ teacher_id: 7, teacher_name: 'Íris', minimum_presence_hours: 12 }] },
    } } } })
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Gerar horário' }))
    fireEvent.click(await screen.findByRole('button', { name: /iniciar gera/i }))
    expect(await screen.findByText(/Íris: mínimo de 12 horas/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Abrir Equipa' })).toHaveAttribute('href', '/members')
    expect(mocks.prevalidation.refetch).toHaveBeenCalled()
  })

  it.each(['approve', 'reject'].flatMap(action => ['school', 'logout', 'unmount'].flatMap(change => ['transient', 'stale'].map(error => [action, change, error]))))(
    'suppresses late %s feedback after %s invalidation for %s errors',
    async (action, change, errorKind) => {
      setClerkState({ userId: 'user_a', orgId: 'org_a' })
      mocks.status = proposalStatus()
      mocks.currentDraft = { proposal_id: 77 }
      let rejectRequest
      mocks[action].mockImplementation(() => new Promise((_resolve, reject) => { rejectRequest = reject }))
      const feedback = vi.spyOn(toast, 'error')
      const page = renderPage()
      fireEvent.click(screen.getByRole('button', { name: action === 'approve' ? 'Aprovar teste' : 'Rejeitar teste' }))
      await waitFor(() => expect(mocks[action]).toHaveBeenCalledTimes(1))
      if (change === 'unmount') page.unmount()
      else {
        act(() => setClerkState(change === 'school' ? { orgId: 'org_b' } : { isSignedIn: false, userId: null, orgId: null }))
        page.rerender(<MemoryRouter initialEntries={['/']}><Schedules /></MemoryRouter>)
      }
      await act(async () => {
        rejectRequest(errorKind === 'stale'
          ? { response: { data: { detail: { code: 'proposal_stale' } } } }
          : new Error('late transport failure'))
      })
      expect(feedback).not.toHaveBeenCalled()
      expect(screen.queryByText(/Existem alterações mais recentes/i)).not.toBeInTheDocument()
    },
  )

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
    expect(await screen.findByText(/proposta pendente é substituída/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /iniciar gera/i }))

    await waitFor(() => {
      expect(mocks.generate).toHaveBeenCalledWith({
        idempotencyKey: expect.any(String),
        expectedInputRevision: 0,
      })
    })
  })

  it('opens the generation review on the first click and only generates after confirmation', async () => {
    mocks.status = proposalStatus({ pending_proposal: null })
    mocks.generate.mockResolvedValue({ job: { id: 92 } })

    renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Gerar horário' }))
    expect(await screen.findByText(/toda a escola/i)).toBeInTheDocument()
    expect(mocks.generate).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: /cancelar/i }))
    await waitFor(() => {
      expect(screen.queryByText(/toda a escola/i)).not.toBeInTheDocument()
    })
    expect(mocks.generate).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Gerar horário' }))
    fireEvent.click(await screen.findByRole('button', { name: /iniciar gera/i }))
    await waitFor(() => {
      expect(mocks.generate).toHaveBeenCalledTimes(1)
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

  it('shows no message when there is no reason to generate', () => {
    mocks.status = proposalStatus({
      eligibility: { can_generate: false, reasons: [], blocker: null },
      pending_proposal: null,
    })

    renderPage()

    expect(screen.queryByRole('button', { name: 'Gerar horário' })).not.toBeInTheDocument()
    expect(screen.queryByText(/Não existem alterações por aplicar ao horário/)).not.toBeInTheDocument()
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
                required_room_type_name: 'Ginásio',
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
    fireEvent.click(await screen.findByRole('button', { name: /iniciar gera/i }))

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
    fireEvent.click(await screen.findByRole('button', { name: /iniciar gera/i }))

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
