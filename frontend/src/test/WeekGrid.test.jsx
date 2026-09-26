import { readFileSync } from 'node:fs'
import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import WeekGrid from '../components/WeekGrid'
import { buildWeekGridModel } from '../utils/weekGridModel'

const baseSlot = {
  active_schedule_block_id: 501,
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

const weekGridCss = readFileSync('src/styles/week-grid.css', 'utf8')

describe('buildWeekGridModel', () => {
  it('builds collisions, baseline times, dates, and locked slots', () => {
    const collision = { ...baseSlot, active_schedule_block_id: 502, week_timesheet_status: 'APPROVED' }
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

  it('builds per-day rows from the range days without touching historical slot times', () => {
    const dayGrids = [
      { date: '2026-09-21', version_id: 1, effective_date: '2025-09-15', blocks: [{ id: 10, day_of_week: 0, start_time: '09:00:00', end_time: '09:50:00' }] },
      { date: '2026-09-22', version_id: 1, effective_date: '2025-09-15', blocks: [] },
      { date: '2026-09-23', version_id: 2, effective_date: '2026-09-23', blocks: [{ id: 11, day_of_week: 2, start_time: '10:00:00', end_time: '10:50:00' }] },
    ]
    const historicalSlot = {
      ...baseSlot,
      timeslot: { id: 12, day_of_week: 0, start_time: '08:00', end_time: '08:50' },
    }
    const model = buildWeekGridModel([baseSlot, historicalSlot], [baseSlot.timeslot], '2026-09-21', dayGrids)

    expect(model.activeDays).toEqual([0, 2])
    expect(model.uniqueTimes).toEqual(['08:00', '09:00', '10:00'])
    expect(model.dayDateMap).toEqual({ 0: '2026-09-21', 2: '2026-09-23' })
    expect(model.endTimeByDay).toEqual({ 0: { '09:00': '09:50' }, 2: { '10:00': '10:50' } })
    expect(model.rowEndTime).toEqual({ '08:00': '08:50', '09:00': null, '10:00': null })
    expect(model.versionByDay).toEqual({
      0: { versionId: 1, effectiveDate: '2025-09-15' },
      2: { versionId: 2, effectiveDate: '2026-09-23' },
    })
    expect(model.slotMap['0:08:00']).toEqual([historicalSlot])
  })

  it('keeps a single row end time when every active day agrees', () => {
    const dayGrids = [
      { date: '2026-09-21', version_id: 3, effective_date: '2026-01-05', blocks: [{ id: 20, day_of_week: 0, start_time: '08:00:00', end_time: '08:50:00' }] },
      { date: '2026-09-23', version_id: 3, effective_date: '2026-01-05', blocks: [{ id: 21, day_of_week: 2, start_time: '08:00:00', end_time: '08:50:00' }] },
    ]
    const model = buildWeekGridModel([], [], '2026-09-21', dayGrids)

    expect(model.rowEndTime).toEqual({ '08:00': '08:50' })
  })
})

describe('WeekGrid (Ponto 8.1)', () => {
  it('uses the viewport-fit density without repeating planned metadata', () => {
    const { container } = render(
      <WeekGrid
        slots={[baseSlot]}
        isLoading={false}
        baseTimeslots={[baseSlot.timeslot]}
        weekStart="2026-04-20"
        fitViewport
      />
    )

    expect(screen.getByRole('table', { name: /grelha semanal/i })).toHaveClass('week-grid--fit-viewport')
    expect(screen.queryByText('Planeado')).not.toBeInTheDocument()
    expect(container.querySelector('.week-grid__time-start')).toHaveTextContent('09:00')
    expect(container.querySelector('.week-grid__time-end')).toHaveTextContent('11:00')
  })

  it('renders a historical slot whose time is absent from the current weekly grid', () => {
    const historical = {
      ...baseSlot,
      timeslot: { id: 12, day_of_week: 0, start_time: '08:00', end_time: '08:50' },
    }
    const dayGrids = [
      {
        date: '2026-09-21',
        version_id: 2,
        effective_date: '2026-09-23',
        blocks: [{ id: 11, day_of_week: 0, start_time: '10:00:00', end_time: '10:50:00' }],
      },
    ]

    const { container } = render(
      <WeekGrid
        slots={[historical]}
        isLoading={false}
        baseTimeslots={[]}
        weekStart="2026-09-21"
        dayGrids={dayGrids}
        gridTransitionDate="2026-09-23"
      />
    )

    const starts = [...container.querySelectorAll('.week-grid__time-start')]
      .map((node) => node.textContent)
    expect(starts).toEqual(['08:00', '10:00'])
    expect(screen.getByText('Programação')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(
      'Nova grelha em vigor a partir de 23/09/2026'
    )
  })

  it('keeps long content readable at the laptop breakpoint', () => {
    const longSlot = {
      ...baseSlot,
      subject: { id: 1, name: 'Programação Avançada de Aplicações Distribuídas' },
      teacher: { id: 7, name: 'Professora Ana Maria Fernandes' },
      room: { id: 3, name: 'Laboratório de Informática 3' },
    }

    render(
      <WeekGrid
        slots={[longSlot]}
        isLoading={false}
        baseTimeslots={[longSlot.timeslot]}
        weekStart="2026-04-20"
        fitViewport
      />
    )

    expect(screen.getByRole('gridcell', {
      name: /Programação Avançada de Aplicações Distribuídas, Professora Ana Maria Fernandes, Laboratório de Informática 3/i,
    })).toBeInTheDocument()
    expect(weekGridCss).toMatch(/@media\s*\(max-width:\s*1399px\)[\s\S]*?week-grid--fit-viewport tbody tr\s*\{[^}]*height:\s*auto/)
    expect(weekGridCss).toMatch(/@media\s*\(max-width:\s*1399px\)[\s\S]*?week-grid--fit-viewport \.week-grid__card\s*\{[^}]*height:\s*auto[^}]*min-height:\s*52px/)
    expect(weekGridCss).toMatch(/@media\s*\(max-width:\s*1399px\)[\s\S]*?week-grid__subject[^}]*white-space:\s*normal[^}]*overflow-wrap:\s*anywhere/)
    expect(weekGridCss).toMatch(/@media\s*\(max-width:\s*1399px\)[\s\S]*?week-grid__secondary[^}]*white-space:\s*normal[^}]*overflow-wrap:\s*anywhere/)
    expect(weekGridCss).toMatch(/@media\s*\(max-width:\s*1399px\)[\s\S]*?week-grid__details[^}]*flex-direction:\s*column[^}]*gap:\s*3px/)
    expect(weekGridCss).toMatch(/@media\s*\(max-width:\s*1399px\)[\s\S]*?week-grid__action[^}]*align-self:\s*flex-end/)
  })

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
        active_schedule_block_id: 501,
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

  it('mostra Concluído na ação e não adiciona linha extra de estado ao concluir aula', () => {
    const completedSlot = {
      ...baseSlot,
      lesson_log_status: 'COMPLETED',
    }

    const { container } = render(
      <WeekGrid
        slots={[completedSlot]}
        isLoading={false}
        baseTimeslots={[completedSlot.timeslot]}
        weekStart="2026-04-20"
        isOperationalEnabled
      />
    )

    expect(screen.getByText('Concluído')).toBeInTheDocument()
    expect(screen.queryByText('Registar')).not.toBeInTheDocument()
    expect(container.querySelector('.week-grid__status')).not.toBeInTheDocument()
    expect(container.querySelector('.week-grid__action--completed')).toHaveTextContent('Concluído')
  })
})

describe('WeekGrid (W07.3 grid versions)', () => {
  const mondaySlot = {
    ...baseSlot,
    date: '2026-09-21',
    active_schedule_block_id: 601,
    timeslot: { id: 20, day_of_week: 0, start_time: '09:00', end_time: '09:50' },
    subject: { id: 2, name: 'Programação' },
  }
  const wednesdaySlot = {
    ...baseSlot,
    date: '2026-09-23',
    active_schedule_block_id: 602,
    timeslot: { id: 21, day_of_week: 2, start_time: '10:00', end_time: '10:50' },
    subject: { id: 3, name: 'Matemática' },
  }
  const dayGrids = [
    { date: '2026-09-21', version_id: 1, effective_date: '2025-09-15', blocks: [{ id: 10, day_of_week: 0, start_time: '09:00:00', end_time: '09:50:00' }] },
    { date: '2026-09-22', version_id: 1, effective_date: '2025-09-15', blocks: [] },
    { date: '2026-09-23', version_id: 2, effective_date: '2026-09-23', blocks: [{ id: 11, day_of_week: 2, start_time: '10:00:00', end_time: '10:50:00' }] },
    { date: '2026-09-24', version_id: 2, effective_date: '2026-09-23', blocks: [] },
  ]

  it('renders each day with its own grid blocks and marks the effective-date change', () => {
    const { container } = render(
      <WeekGrid
        slots={[mondaySlot, wednesdaySlot]}
        isLoading={false}
        baseTimeslots={[mondaySlot.timeslot, wednesdaySlot.timeslot]}
        weekStart="2026-09-21"
        dayGrids={dayGrids}
        gridTransitionDate="2026-09-23"
      />
    )

    const rows = container.querySelectorAll('tbody tr')
    expect(rows).toHaveLength(2)
    expect(within(rows[0]).getByText('Programação')).toBeInTheDocument()
    expect(within(rows[0]).queryByText('Matemática')).not.toBeInTheDocument()
    expect(within(rows[1]).getByText('Matemática')).toBeInTheDocument()
    expect(within(rows[1]).queryByText('Programação')).not.toBeInTheDocument()

    const timeCells = container.querySelectorAll('.week-grid__time')
    expect(timeCells).toHaveLength(2)
    expect(timeCells[0]).toHaveAttribute('aria-label', '09:00')
    expect(timeCells[0].querySelector('.week-grid__time-end')).toHaveTextContent('')
    expect(timeCells[1]).toHaveAttribute('aria-label', '10:00')
    expect(timeCells[1].querySelector('.week-grid__time-end')).toHaveTextContent('')

    expect(screen.getByRole('status')).toHaveTextContent('Nova grelha em vigor a partir de 23/09/2026')

    const badge = screen.getByTitle('Nova grelha em vigor a partir de 23/09/2026')
    expect(badge).toHaveTextContent('Nova grelha')
    expect(badge).toHaveAttribute('aria-label', 'Nova grelha em vigor a partir de 23/09/2026')
    expect(screen.getAllByText('Nova grelha')).toHaveLength(1)
  })

  it('keeps the previous rendering when dayGrids is absent', () => {
    const { container } = render(
      <WeekGrid
        slots={[baseSlot]}
        isLoading={false}
        baseTimeslots={[baseSlot.timeslot]}
        weekStart="2026-04-20"
      />
    )

    const timeCell = container.querySelector('.week-grid__time')
    expect(timeCell.querySelector('.week-grid__time-start')).toHaveTextContent('09:00')
    expect(timeCell.querySelector('.week-grid__time-end')).toHaveTextContent('11:00')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(container.querySelector('.week-grid__version-badge')).not.toBeInTheDocument()
  })
})
