import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import GenerationStatusPanel from '../components/schedules/GenerationStatusPanel'
import { useScheduleTaskStatus } from '../hooks/useSchoolData'

vi.mock('../hooks/useSchoolData', () => ({
  useScheduleTaskStatus: vi.fn(),
}))

describe('GenerationStatusPanel', () => {
  afterEach(cleanup)

  it.each([
    ['NO_VALID_OUTPUT', 'Não foi possível gerar um horário válido'],
    ['CANCELED', 'Geração cancelada'],
    ['FAILED', 'Erro na geração'],
  ])('shows a clear terminal message for %s', (jobStatus, expected) => {
    useScheduleTaskStatus.mockReturnValue({ data: { job_status: jobStatus } })

    render(<GenerationStatusPanel jobId={12} />)

    expect(screen.getByText(expected)).toBeInTheDocument()
  })

  it('shows the server failure detail for a timed-out job', () => {
    useScheduleTaskStatus.mockReturnValue({
      data: {
        job_status: 'FAILED',
        failure_code: 'TIMEOUT',
        failure_message: 'A geração excedeu o limite de cinco minutos.',
      },
    })

    render(<GenerationStatusPanel jobId={13} />)

    expect(screen.getByText(/excedeu o limite de cinco minutos/i)).toBeInTheDocument()
  })
})
