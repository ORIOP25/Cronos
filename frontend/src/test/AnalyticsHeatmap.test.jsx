import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AnalyticsHeatmap from '../components/AnalyticsHeatmap'

const mocks = vi.hoisted(() => ({ heatmap: [] }))

vi.mock('../features/catalog/data', () => ({
  useTimeslots: () => ({ data: [{ id: 1, day_of_week: 0, start_time: '09:00:00' }], isLoading: false, isError: false }),
}))
vi.mock('../features/schoolConfig/data', () => ({
  useAvailabilityHeatmap: () => ({ data: mocks.heatmap, isLoading: false, isError: false }),
}))

describe('AnalyticsHeatmap', () => {
  it('shows the grid without a block count sentence', () => {
    mocks.heatmap = [{ timeslot_id: 1, available_count: 3, total_teachers: 4, availability_ratio: 0.75 }]
    render(<AnalyticsHeatmap />)

    expect(screen.getByLabelText('Seg às 09:00: 3 de 4 professores disponíveis')).toBeInTheDocument()
    expect(screen.queryByText(/A grelha mostra/)).not.toBeInTheDocument()
  })

  it('says when there is no availability data yet', () => {
    mocks.heatmap = []
    render(<AnalyticsHeatmap />)

    expect(screen.getByText('Ainda não existem dados de disponibilidade para estes blocos.')).toBeInTheDocument()
  })
})
