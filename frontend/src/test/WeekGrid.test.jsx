import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import WeekGrid from '../components/WeekGrid'
import { buildWeekGridModel } from '../utils/weekGridModel'

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

describe('buildWeekGridModel', () => {
  it('builds collisions, baseline times, dates, and locked slots', () => {
    const collision = { ...baseSlot, schedule_output_id: 502, week_timesheet_status: 'APPROVED' }
    const baseline = { id: 10, day_of_week: 1, start_time: '11:00:00', end_time: '12:00:00' }
    const model = buildWeekGridModel([baseSlot, collision], [baseSlot.timeslot, baseline], '2026-04-20')
    expect(model.slotMap['0:09:00']).toHaveLength(2)
    expect(model.slotMap['0:09:00'][1].week_timesheet_status).toBe('APPROVED')
    expect(model.uniqueTimes).toEqual(['09:00', '11:00'])
    expect(model.activeDays).toEqual([0, 1])
    expect(model.dayDateMap).toEqual({ 0: '2026-04-20', 1: '2026-04-21' })
  })

  it('supports empty input', () => {
    expect(buildWeekGridModel()).toEqual({ slotMap: {}, uniqueTimes: [], activeDays: [], endTimeMap: {}, dayDateMap: {} })
  })
})

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
    expect(onOpenOperationalAction).toHaveBeenCalledWith(expect.objectContaining({
      ...baseSlot,
      can_create_occurrence: true,
      can_decide_occurrence: false,
    }))
  })

  it('opens an active baseline block for operational registration', () => {
    const onOpenOperationalAction = vi.fn()
    const activeSlot = {
      ...baseSlot,
      schedule_output_id: null,
      active_schedule_block_id: 902,
      block_source: 'active',
    }

    render(
      <WeekGrid
        slots={[activeSlot]}
        isLoading={false}
        baseTimeslots={[activeSlot.timeslot]}
        weekStart="2026-04-20"
        isOperationalEnabled
        onOpenOperationalAction={onOpenOperationalAction}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: /abrir registo/i }))
    expect(onOpenOperationalAction).toHaveBeenCalledWith(
      expect.objectContaining({
        active_schedule_block_id: 902,
        block_source: 'active',
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

  it('permite ação operacional em bloco passado quando há ação válida', () => {
    const onOpenOperationalAction = vi.fn()
    const pastSlot = {
      ...baseSlot,
      is_past: true,
      can_create_occurrence: true,
      can_decide_occurrence: false,
    }

    render(
      <WeekGrid
        slots={[pastSlot]}
        isLoading={false}
        baseTimeslots={[pastSlot.timeslot]}
        weekStart="2026-04-20"
        isOperationalEnabled
        onOpenOperationalAction={onOpenOperationalAction}
      />
    )

    const slotButton = screen.getByRole('button', { name: /programação/i })
    fireEvent.click(slotButton)

    expect(onOpenOperationalAction).toHaveBeenCalledTimes(1)
  })

  it('mostra orientação quando ocorrência já está fechada', () => {
    const onOpenOperationalAction = vi.fn()
    const closedOccurrenceSlot = {
      ...baseSlot,
      is_past: true,
      occurrence_id: 777,
      occurrence_status: 'GIVEN',
      occurrence_decided_at: '2026-04-20T10:00:00Z',
      can_create_occurrence: false,
      can_decide_occurrence: false,
    }

    render(
      <WeekGrid
        slots={[closedOccurrenceSlot]}
        isLoading={false}
        baseTimeslots={[closedOccurrenceSlot.timeslot]}
        weekStart="2026-04-20"
        isOperationalEnabled
        onOpenOperationalAction={onOpenOperationalAction}
      />
    )

    const slotButton = screen.getByRole('button', { name: /programação/i })
    expect(slotButton).toBeInTheDocument()
  })
})
