import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import GenerationStatusPanel from '../components/schedules/GenerationStatusPanel'
import { useScheduleTaskStatus } from '../features/scheduling/data'

vi.mock('../features/scheduling/data', () => ({
  useScheduleTaskStatus: vi.fn(),
}))

describe('GenerationStatusPanel', () => {
  afterEach(cleanup)

  it('explains that an inconclusive search is not an impossibility', () => {
    useScheduleTaskStatus.mockReturnValue({ data: { status: 'INCONCLUSIVE' } })

    render(<GenerationStatusPanel jobId={13} />)

    expect(screen.getByText(/não significa que o horário seja impossível/i)).toBeInTheDocument()
  })

  it('explains an availability conflict with protected lessons and links to configuration', () => {
    useScheduleTaskStatus.mockReturnValue({
      data: {
        status: 'INFEASIBLE',
        diagnostics: [{ code: 'PROTECTED_AVAILABILITY_CONFLICT' }],
      },
    })

    render(<MemoryRouter><GenerationStatusPanel jobId={40} /></MemoryRouter>)

    expect(screen.getByText(/aulas protegidas.*Impossível/)).toBeInTheDocument()
    expect(screen.getByText(/disponibilidade ou a janela de proteção/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /abrir configuração/i })).toHaveAttribute('href', '/config')
    expect(screen.queryByText(/não significa que o horário seja impossível/i)).toBeNull()
  })

  it('shows an honest queue position without fake progress', () => {
    useScheduleTaskStatus.mockReturnValue({
      data: { status: 'QUEUED', queue_position: 3, queued_at: new Date().toISOString() },
    })

    render(<GenerationStatusPanel jobId={14} />)

    expect(screen.getByText(/3\.º pedido em espera/i)).toBeInTheDocument()
  })

  it('offers a retry when loading the job fails temporarily', () => {
    const refetch = vi.fn()
    useScheduleTaskStatus.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: { response: { status: 503 } },
      refetch,
    })

    render(<GenerationStatusPanel jobId={15} />)

    screen.getByRole('button', { name: /tentar novamente/i }).click()
    expect(refetch).toHaveBeenCalledOnce()
  })

  it('links to login for an expired session without retry looping', () => {
    useScheduleTaskStatus.mockReturnValue({
      isLoading: false,
      isError: true,
      error: { response: { status: 401 } },
      refetch: vi.fn(),
    })

    render(<GenerationStatusPanel jobId={16} />)

    expect(screen.getByRole('link', { name: /entrar novamente/i })).toHaveAttribute('href', '/login')
    expect(screen.queryByRole('button', { name: /tentar novamente/i })).toBeNull()
  })

  it('shows access guidance for forbidden status without retry', () => {
    useScheduleTaskStatus.mockReturnValue({
      isLoading: false,
      isError: true,
      error: { response: { status: 403 } },
      refetch: vi.fn(),
    })

    render(<GenerationStatusPanel jobId={17} />)

    expect(screen.getByText(/não tem permissão/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /tentar novamente/i })).toBeNull()
  })

  it('shows error feedback for a failed generation', () => {
    useScheduleTaskStatus.mockReturnValue({ data: { status: 'FAILED' } })

    render(<GenerationStatusPanel jobId={20} />)

    expect(screen.getByTestId('generation-terminal')).toBeInTheDocument()
    expect(screen.getByText('Não foi possível concluir a geração')).toBeInTheDocument()
    expect(screen.getByText(/Ocorreu um erro durante a geração/)).toBeInTheDocument()
  })

  it('treats an unrecognized status as a generation failure', () => {
    useScheduleTaskStatus.mockReturnValue({ data: { status: 'UNRECOGNIZED' } })

    render(<GenerationStatusPanel jobId={21} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Geração não iniciada')
  })

  it('keeps the success state when the job completes', () => {
    useScheduleTaskStatus.mockReturnValue({ data: { status: 'SUCCEEDED' }, isLoading: false })

    render(<GenerationStatusPanel jobId={18} />)

    expect(screen.getByText(/proposta pronta/i)).toBeInTheDocument()
  })

  it('points to rooms when generation stopped for an incompatible room', () => {
    useScheduleTaskStatus.mockReturnValue({
      data: { status: 'FAILED', stop_reason: 'NO_ELIGIBLE_ROOM' },
      isLoading: false,
    })

    render(
      <MemoryRouter>
        <GenerationStatusPanel jobId={19} />
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: /abrir salas/i })).toHaveAttribute('href', '/rooms')
  })

  it('links the classes and subjects of proven infeasible diagnostics with hours and minutes', () => {
    useScheduleTaskStatus.mockReturnValue({
      data: {
        status: 'INFEASIBLE',
        diagnostics: [
          { code: 'INSUFFICIENT_CLASS_TIME', minimum_missing_minutes: 200, class_id: 5, class_name: 'TGEI 25/28', course_id: 7, subject_name: null },
          { code: 'INSUFFICIENT_INTERSECTION', minimum_missing_minutes: 90, class_id: 6, class_name: 'TM 24/27', course_id: 8, subject_name: 'Matemática' },
        ],
      },
      isLoading: false,
    })

    render(
      <MemoryRouter>
        <GenerationStatusPanel jobId={30} />
      </MemoryRouter>,
    )

    expect(screen.getByText(/Turmas sem tempo suficiente/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'TGEI 25/28' })).toHaveAttribute('href', '/courses/7/classes/5')
    expect(screen.getByText(/faltam pelo menos 3 h 20 min\./)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'TM 24/27' })).toHaveAttribute('href', '/courses/8/classes/6')
    expect(screen.getByText(/Matemática/)).toBeInTheDocument()
    expect(screen.getByText(/faltam pelo menos 1 h 30 min em que a turma e o professor estejam livres\./)).toBeInTheDocument()
    expect(screen.getByText(/Reveja a disponibilidade destas turmas\./)).toBeInTheDocument()
  })

  it('keeps the generic message when a class diagnostic has no proven name', () => {
    useScheduleTaskStatus.mockReturnValue({
      data: {
        status: 'INFEASIBLE',
        diagnostics: [
          { code: 'INSUFFICIENT_CLASS_TIME', minimum_missing_minutes: 60, class_id: 5, class_name: null, course_id: null, subject_name: null },
        ],
      },
      isLoading: false,
    })

    render(
      <MemoryRouter>
        <GenerationStatusPanel jobId={31} />
      </MemoryRouter>,
    )

    expect(screen.getByText(/Reveja disponibilidades, salas, professor atribuído ou datas/)).toBeInTheDocument()
    expect(screen.queryByText(/Turmas sem tempo suficiente/)).toBeNull()
  })

  it('does not claim a known class or a zero deficit when the missing minutes are absent', () => {
    useScheduleTaskStatus.mockReturnValue({
      data: {
        status: 'INFEASIBLE',
        diagnostics: [
          { code: 'INSUFFICIENT_CLASS_TIME', minimum_missing_minutes: null, class_id: 5, class_name: 'TGEI 25/28', course_id: 7, subject_name: null },
          { code: 'INSUFFICIENT_INTERSECTION', minimum_missing_minutes: null, class_id: 6, class_name: 'TM 24/27', course_id: 8, subject_name: 'Matemática' },
        ],
      },
      isLoading: false,
    })

    render(
      <MemoryRouter>
        <GenerationStatusPanel jobId={32} />
      </MemoryRouter>,
    )

    expect(screen.getByText(/Reveja disponibilidades, salas, professor atribuído ou datas/)).toBeInTheDocument()
    expect(screen.queryByText(/Turmas sem tempo suficiente/)).toBeNull()
    expect(screen.queryByText(/TGEI 25\/28/)).toBeNull()
    expect(screen.queryByText(/0 min/)).toBeNull()
  })

  it('explains a joint lesson with no common free time from result_code', () => {
    useScheduleTaskStatus.mockReturnValue({
      data: { status: 'INFEASIBLE', result_code: 'JOINT_NO_COMMON_TIME' },
      isLoading: false,
    })

    render(
      <MemoryRouter>
        <GenerationStatusPanel jobId={22} />
      </MemoryRouter>,
    )

    expect(screen.getByText(/não têm horas livres em comum/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /abrir configuração/i })).toHaveAttribute('href', '/config')
  })

  it('names the joint classes and the subject from the typed diagnostics', () => {
    useScheduleTaskStatus.mockReturnValue({
      data: {
        status: 'INFEASIBLE',
        result_code: 'JOINT_NO_COMMON_TIME',
        diagnostics: [
          { code: 'JOINT_NO_COMMON_TIME', minimum_missing_minutes: null, class_id: 5, class_name: 'TGEI 25/28', course_id: 7, subject_name: 'Matemática' },
          { code: 'JOINT_NO_COMMON_TIME', minimum_missing_minutes: null, class_id: 6, class_name: 'TM 24/27', course_id: 8, subject_name: 'Matemática' },
        ],
      },
      isLoading: false,
    })

    render(
      <MemoryRouter>
        <GenerationStatusPanel jobId={40} />
      </MemoryRouter>,
    )

    expect(
      screen.getByText('As turmas TGEI 25/28, TM 24/27 não têm horas livres em comum para Matemática.'),
    ).toBeInTheDocument()
  })

  it('falls back to the generic joint message when a member class name is unresolved', () => {
    useScheduleTaskStatus.mockReturnValue({
      data: {
        status: 'INFEASIBLE',
        result_code: 'JOINT_NO_COMMON_TIME',
        diagnostics: [
          { code: 'JOINT_NO_COMMON_TIME', minimum_missing_minutes: null, class_id: 5, class_name: 'TGEI 25/28', course_id: 7, subject_name: 'Matemática' },
          { code: 'JOINT_NO_COMMON_TIME', minimum_missing_minutes: null, class_id: 6, class_name: null, course_id: null, subject_name: 'Matemática' },
        ],
      },
      isLoading: false,
    })

    render(
      <MemoryRouter>
        <GenerationStatusPanel jobId={41} />
      </MemoryRouter>,
    )

    expect(screen.getByText(/As turmas da aula conjunta não têm horas livres em comum\./)).toBeInTheDocument()
    expect(screen.queryByText(/TGEI 25\/28/)).toBeNull()
  })

  it('falls back to the generic joint message when the subject name is unresolved', () => {
    useScheduleTaskStatus.mockReturnValue({
      data: {
        status: 'INFEASIBLE',
        result_code: 'JOINT_NO_COMMON_TIME',
        diagnostics: [
          { code: 'JOINT_NO_COMMON_TIME', minimum_missing_minutes: null, class_id: 5, class_name: 'TGEI 25/28', course_id: 7, subject_name: null },
          { code: 'JOINT_NO_COMMON_TIME', minimum_missing_minutes: null, class_id: 6, class_name: 'TM 24/27', course_id: 8, subject_name: null },
        ],
      },
      isLoading: false,
    })

    render(
      <MemoryRouter>
        <GenerationStatusPanel jobId={42} />
      </MemoryRouter>,
    )

    expect(screen.getByText(/As turmas da aula conjunta não têm horas livres em comum\./)).toBeInTheDocument()
  })

  it('renders a hostile class name as text, never as markup', () => {
    useScheduleTaskStatus.mockReturnValue({
      data: {
        status: 'INFEASIBLE',
        result_code: 'JOINT_NO_COMMON_TIME',
        diagnostics: [
          { code: 'JOINT_NO_COMMON_TIME', minimum_missing_minutes: null, class_id: 5, class_name: '<img src=x onerror=alert(1)>', course_id: 7, subject_name: 'Matemática' },
          { code: 'JOINT_NO_COMMON_TIME', minimum_missing_minutes: null, class_id: 6, class_name: 'TM 24/27', course_id: 8, subject_name: 'Matemática' },
        ],
      },
      isLoading: false,
    })

    const { container } = render(
      <MemoryRouter>
        <GenerationStatusPanel jobId={43} />
      </MemoryRouter>,
    )

    expect(container.querySelector('img')).toBeNull()
    expect(screen.getByText(/<img src=x onerror=alert\(1\)>/)).toBeInTheDocument()
  })

  it('explains a joint lesson with no common free time from stop_reason', () => {
    useScheduleTaskStatus.mockReturnValue({
      data: { status: 'FAILED', stop_reason: 'JOINT_NO_COMMON_TIME' },
      isLoading: false,
    })

    render(
      <MemoryRouter>
        <GenerationStatusPanel jobId={23} />
      </MemoryRouter>,
    )

    expect(screen.getByText(/não têm horas livres em comum/i)).toBeInTheDocument()
  })

  it('keeps the generic infeasible message without a joint code', () => {
    useScheduleTaskStatus.mockReturnValue({ data: { status: 'INFEASIBLE' }, isLoading: false })

    render(
      <MemoryRouter>
        <GenerationStatusPanel jobId={24} />
      </MemoryRouter>,
    )

    expect(screen.getByText(/Reveja disponibilidades, salas, professor atribuído ou datas/)).toBeInTheDocument()
    expect(screen.queryByText(/não têm horas livres em comum/i)).not.toBeInTheDocument()
  })

  it('keeps the stale message when the data changed during generation', () => {
    useScheduleTaskStatus.mockReturnValue({
      data: { status: 'STALE', stop_reason: 'JOINT_NO_COMMON_TIME' },
      isLoading: false,
    })

    render(
      <MemoryRouter>
        <GenerationStatusPanel jobId={26} />
      </MemoryRouter>,
    )

    expect(screen.getByText(/Os dados da escola mudaram durante a geração/)).toBeInTheDocument()
    expect(screen.queryByText(/não têm horas livres em comum/i)).not.toBeInTheDocument()
  })

  it('points to rooms when a joint lesson lacks a compatible room', () => {
    useScheduleTaskStatus.mockReturnValue({
      data: { status: 'FAILED', stop_reason: 'JOINT_ROOM_CAPACITY' },
      isLoading: false,
    })

    render(
      <MemoryRouter>
        <GenerationStatusPanel jobId={25} />
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: /abrir salas/i })).toHaveAttribute('href', '/rooms')
  })
})
