import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Schedules from '../pages/Schedules'
import { renderWithProviders } from './testUtils'
import { useAuthStore } from '../store'
import * as schoolHooks from '../hooks/useSchoolData'

const { mockNavigate } = vi.hoisted(() => ({
  mockNavigate: vi.fn(),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

vi.mock('../hooks/useSchoolData', () => ({
  useDrafts: vi.fn(),
  useScheduleDiff: vi.fn(),
  useApproveDraft: vi.fn(),
  useRejectDraft: vi.fn(),
  useGenerateSchedule: vi.fn(),
  useCancelScheduleTask: vi.fn(),
  useScheduleTaskStatus: vi.fn(),
  useClasses: vi.fn(),
  useTeachers: vi.fn(),
  useWeekSchedule: vi.fn(),
  useClassDetails: vi.fn(),
  useTimeslots: vi.fn(),
  useCreateOccurrence: vi.fn(),
}))

const baseTimeslot = {
  id: 1,
  day_of_week: 0,
  start_time: '09:00',
  end_time: '11:00',
}

const buildSlot = (overrides = {}) => ({
  schedule_output_id: 501,
  date: '2026-04-21',
  timeslot: baseTimeslot,
  subject: { id: 10, name: 'Programacao' },
  teacher: { id: 20, name: 'Prof. Ana' },
  room: { id: 30, name: 'Sala 101' },
  class_info: { id: 1, name: '10TGPSI' },
  is_past: false,
  occurrence_status: null,
  hours_given: null,
  ...overrides,
})

const setupBaseHooks = ({
  weekSlots,
  createOccurrenceMutation,
  drafts = [],
  scheduleDiff = null,
  approveDraftMutation = {
    mutateAsync: vi.fn(),
    isPending: false,
  },
  rejectDraftMutation = {
    mutateAsync: vi.fn(),
    isPending: false,
  },
  generateMutation = {
    mutateAsync: vi.fn(),
    isPending: false,
  },
  taskStatusData = null,
  cancelGenerationMutation = { mutate: vi.fn(), isPending: false },
}) => {
  schoolHooks.useDrafts.mockReturnValue({ data: drafts, refetch: vi.fn() })
  schoolHooks.useScheduleDiff.mockReturnValue({ data: scheduleDiff, isLoading: false })
  schoolHooks.useGenerateSchedule.mockReturnValue(generateMutation)
  schoolHooks.useCancelScheduleTask.mockReturnValue(cancelGenerationMutation)
  schoolHooks.useApproveDraft.mockReturnValue(approveDraftMutation)
  schoolHooks.useRejectDraft.mockReturnValue(rejectDraftMutation)
  schoolHooks.useScheduleTaskStatus.mockImplementation((taskId) => ({
    data: taskId ? taskStatusData : null,
  }))
  schoolHooks.useClasses.mockReturnValue({ data: [{ id: 1, name: '10TGPSI' }] })
  schoolHooks.useTeachers.mockReturnValue({ data: [] })
  schoolHooks.useTimeslots.mockReturnValue({ data: [baseTimeslot] })
  schoolHooks.useWeekSchedule.mockReturnValue({
    data: weekSlots,
    isFetching: false,
    isError: false,
  })
  schoolHooks.useClassDetails.mockReturnValue({ data: { subjects: [] } })
  schoolHooks.useCreateOccurrence.mockReturnValue(createOccurrenceMutation)
}

const renderPage = () => {
  return renderWithProviders(
    <MemoryRouter>
      <Schedules />
    </MemoryRouter>
  )
}

const selectClass = () => {
  fireEvent.change(screen.getByLabelText('Turma'), {
    target: { value: '1' },
  })
}

describe('Schedules operational flow (Ponto 13 pacote G)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        email: 'admin@escola.pt',
        role: 'admin',
        teacherId: null,
        orgId: 1,
      },
    })
  })

  it('navigates directly to absences when block already has occurrence', async () => {
    const createOccurrenceMutation = {
      mutate: vi.fn(),
      isPending: false,
    }

    setupBaseHooks({
      weekSlots: [buildSlot({
        occurrence_id: 321,
        can_create_occurrence: false,
        can_decide_occurrence: true,
        occurrence_status: 'GAP',
      })],
      createOccurrenceMutation,
    })

    renderPage()
    selectClass()

    fireEvent.click(screen.getByRole('button', { name: /programacao/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Ir para Faltas' }))

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith(
        '/absences?occurrence_id=321&class_id=1'
      )
    })
    expect(createOccurrenceMutation.mutate).not.toHaveBeenCalled()
  })

  it('creates occurrence from block and navigates with contextual params', async () => {
    const createOccurrenceMutation = {
      mutate: vi.fn((variables, options) => {
        expect(variables).toEqual({ scheduleOutputId: 501 })
        options.onSuccess({ id: 777 })
      }),
      isPending: false,
    }

    setupBaseHooks({
      weekSlots: [buildSlot({
        occurrence_id: null,
        can_create_occurrence: true,
        can_decide_occurrence: false,
      })],
      createOccurrenceMutation,
    })

    renderPage()
    selectClass()

    fireEvent.click(screen.getByRole('button', { name: /programacao/i }))
    const dialog = screen.getByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: /Criar Ocorr/ }))

    await waitFor(() => {
      expect(createOccurrenceMutation.mutate).toHaveBeenCalledTimes(1)
      expect(mockNavigate).toHaveBeenCalledWith(
        '/absences?occurrence_id=777&class_id=1'
      )
    })
  })

  it('restores active generation after remount using persisted task id', async () => {
    const taskId = 'task-running-restore'
    const createOccurrenceMutation = {
      mutate: vi.fn(),
      isPending: false,
    }
    const generateMutation = {
      mutateAsync: vi.fn().mockResolvedValue({ task_id: taskId }),
      isPending: false,
    }

    setupBaseHooks({
      weekSlots: [],
      createOccurrenceMutation,
      generateMutation,
      taskStatusData: {
        status: 'SOLVING',
        detail: 'A otimizar com CP-SAT.',
      },
    })

    const firstRender = renderPage()

    fireEvent.click(screen.getByRole('button', { name: /Gerar Horário/i }))

    await waitFor(() => {
      expect(localStorage.getItem('hz-schedule-active-task-org-1')).toBe(taskId)
    })

    firstRender.unmount()

    renderPage()

    expect(await screen.findByText(/A calcular o melhor horário para a escola/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Cancelar geração/i })).toBeInTheDocument()
  })

  it('calls cancel mutation with the active generation task id', async () => {
    const taskId = 'task-running-cancel'
    const createOccurrenceMutation = {
      mutate: vi.fn(),
      isPending: false,
    }
    const generateMutation = {
      mutateAsync: vi.fn().mockResolvedValue({ task_id: taskId }),
      isPending: false,
    }
    const cancelGenerationMutation = {
      mutate: vi.fn(),
      isPending: false,
    }

    setupBaseHooks({
      weekSlots: [],
      createOccurrenceMutation,
      generateMutation,
      taskStatusData: {
        status: 'SOLVING',
        detail: 'A otimizar com CP-SAT.',
      },
      cancelGenerationMutation,
    })

    renderPage()

    fireEvent.click(screen.getByRole('button', { name: /Gerar Horário/i }))

    const cancelButton = await screen.findByRole('button', { name: /Cancelar geração/i })
    fireEvent.click(cancelButton)

    await waitFor(() => {
      expect(cancelGenerationMutation.mutate).toHaveBeenCalledTimes(1)
    })

    const [calledTaskId, callbackOptions] = cancelGenerationMutation.mutate.mock.calls[0]
    expect(calledTaskId).toBe(taskId)
    expect(typeof callbackOptions?.onSuccess).toBe('function')
    expect(typeof callbackOptions?.onError).toBe('function')
  })

  it('approves draft after user clicks the button in draft panel', async () => {
    const approveDraftMutation = {
      mutateAsync: vi.fn().mockResolvedValue({ blocks_activated: 8 }),
      isPending: false,
    }

    setupBaseHooks({
      weekSlots: [],
      createOccurrenceMutation: { mutate: vi.fn(), isPending: false },
      drafts: [
        {
          generation_id: 'gen-draft-human-001',
          count: 12,
          earliest_date: '2026-05-10',
          latest_date: '2026-06-20',
        },
      ],
      scheduleDiff: { added: 3, removed: 1, unchanged: 20 },
      approveDraftMutation,
    })

    renderPage()

    fireEvent.click(screen.getByRole('button', { name: /Aprovar e Ativar/i }))

    await waitFor(() => {
      expect(approveDraftMutation.mutateAsync).toHaveBeenCalledWith('gen-draft-human-001')
    })
  })

  it('rejects draft after user clicks the reject button', async () => {
    const rejectDraftMutation = {
      mutateAsync: vi.fn().mockResolvedValue({ blocks_deleted: 12 }),
      isPending: false,
    }

    setupBaseHooks({
      weekSlots: [],
      createOccurrenceMutation: { mutate: vi.fn(), isPending: false },
      drafts: [
        {
          generation_id: 'gen-draft-human-002',
          count: 12,
          earliest_date: '2026-05-10',
          latest_date: '2026-06-20',
        },
      ],
      scheduleDiff: { added: 2, removed: 4, unchanged: 11 },
      rejectDraftMutation,
    })

    renderPage()

    fireEvent.click(screen.getByRole('button', { name: /Rejeitar/i }))

    await waitFor(() => {
      expect(rejectDraftMutation.mutateAsync).toHaveBeenCalledWith('gen-draft-human-002')
    })
  })
})