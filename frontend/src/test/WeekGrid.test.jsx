import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import WeekGrid from '../components/WeekGrid'

const baseSlot = {
  schedule_output_id: 501,
  date: '2026-04-20',
  timeslot: {
    id: 9,
    day_of_week: 0,
    start_time: '09:00',
    end_time: '11:00',
  },
  subject: { id: 1, name: 'Programação' },
  teacher: { id: 7, name: 'Prof. Ana' },
  room: { id: 3, name: 'Sala 101' },
  class_info: { id: 11, name: '10TGPSI' },
  module: { id: 5, name: 'M1', hours_total: 25 },
  is_past: false,
  occurrence_status: null,
  hours_given: null,
}

describe('WeekGrid (Ponto 8.1)', () => {
  it('abre ação operacional ao clicar em bloco elegível', () => {
    const onOpenOperationalAction = vi.fn()

    render(
      <WeekGrid
        slots={[baseSlot]}
        isLoading={false}
        baseTimeslots={[baseSlot.timeslot]}
        weekStart="2026-04-20"
        isOperationalEnabled
        onOpenOperationalAction={onOpenOperationalAction}
      />
    )

    const slotButton = screen.getByRole('button', { name: /programação/i })
    fireEvent.click(slotButton)

    expect(onOpenOperationalAction).toHaveBeenCalledTimes(1)
    expect(onOpenOperationalAction).toHaveBeenCalledWith(
      expect.objectContaining({
        schedule_output_id: 501,
        date: '2026-04-20',
      })
    )
  })

  it('mantém bloco em modo leitura quando ação operacional está desativada', () => {
    const onOpenOperationalAction = vi.fn()

    render(
      <WeekGrid
        slots={[baseSlot]}
        isLoading={false}
        baseTimeslots={[baseSlot.timeslot]}
        weekStart="2026-04-20"
        isOperationalEnabled={false}
        onOpenOperationalAction={onOpenOperationalAction}
      />
    )

    const slotButton = screen.getByRole('button', { name: /programação/i })
    expect(slotButton).toBeDisabled()
    fireEvent.click(slotButton)
    expect(onOpenOperationalAction).not.toHaveBeenCalled()
  })

  it('abre ação de ir para faltas quando ocorrência já existe', () => {
    const onOpenOperationalAction = vi.fn()
    const slotWithOccurrence = {
      ...baseSlot,
      occurrence_id: 321,
      occurrence_status: 'GAP',
      can_create_occurrence: false,
      can_decide_occurrence: true,
    }

    render(
      <WeekGrid
        slots={[slotWithOccurrence]}
        isLoading={false}
        baseTimeslots={[slotWithOccurrence.timeslot]}
        weekStart="2026-04-20"
        isOperationalEnabled
        onOpenOperationalAction={onOpenOperationalAction}
      />
    )

    const slotButton = screen.getByRole('button', { name: /programação/i })
    fireEvent.click(slotButton)

    expect(onOpenOperationalAction).toHaveBeenCalledTimes(1)
    expect(onOpenOperationalAction).toHaveBeenCalledWith(
      expect.objectContaining({
        schedule_output_id: 501,
        occurrence_id: 321,
        can_create_occurrence: false,
        can_decide_occurrence: true,
      })
    )
  })
})
