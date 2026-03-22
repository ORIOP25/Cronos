import React, { useMemo } from 'react'
import PropTypes from 'prop-types'
import { CSpinner } from '@coreui/react'
import { getSubjectColor } from '../utils/subjectColors'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const DAY_LABELS = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']

const OCCURRENCE_STYLES = {
  GIVEN:       { backgroundColor: '#d1e7dd', borderLeft: '3px solid #198754' },
  GAP:         { backgroundColor: '#f8d7da', borderLeft: '3px solid #dc3545' },
  SUBSTITUTED: { backgroundColor: '#fff3cd', borderLeft: '3px solid #ffc107' },
}

const OCCURRENCE_LABELS = {
  GIVEN:       'Dado ✓',
  GAP:         'Furo ✗',
  SUBSTITUTED: 'Substituído ↔',
}

function normalizeTimeLabel(value) {
  if (!value) return ''
  const text = String(value)
  if (text.length >= 5) {
    return text.slice(0, 5)
  }
  return text
}

// ---------------------------------------------------------------------------
// Pure helpers — outside component (SonarQube S7721)
// ---------------------------------------------------------------------------

/** Build a lookup map: "dayOfWeek:startTime" → slot */
function buildSlotMap(slots) {
  const map = {}
  slots.forEach(slot => {
    const key = `${slot.timeslot.day_of_week}:${normalizeTimeLabel(slot.timeslot.start_time)}`
    map[key] = slot
  })
  return map
}

/** Compute the CSS style for a cell based on occurrence status. */
function getCellStyle(slot) {
  if (!slot) return {}
  const color = getSubjectColor(slot.subject?.id ?? 0)

  if (!slot.is_past) {
    return {
      backgroundColor: `${color}26`,   // ~15% opacity
      borderLeft: `3px solid ${color}`,
    }
  }

  if (slot.occurrence_status && OCCURRENCE_STYLES[slot.occurrence_status]) {
    return OCCURRENCE_STYLES[slot.occurrence_status]
  }

  // Past but no occurrence registered yet
  return { backgroundColor: '#e9ecef', borderLeft: `3px solid ${color}` }
}

/** Format a date string as "04 Mar" for column headers. */
function formatDateLabel(dateStr) {
  if (!dateStr) return ''
  return new Date(`${dateStr}T12:00:00`).toLocaleDateString('pt-PT', {
    day: '2-digit',
    month: 'short',
  })
}

function getDateForDayFromWeekStart(weekStart, dayOfWeek) {
  if (!weekStart) return ''
  const date = new Date(`${weekStart}T12:00:00`)
  date.setDate(date.getDate() + dayOfWeek)
  return date.toISOString().split('T')[0]
}

// ---------------------------------------------------------------------------
// SlotCell — individual table cell
// ---------------------------------------------------------------------------
const SlotCell = ({ slot }) => {
  if (!slot) {
    return (
      <td className="bg-light text-center align-middle" style={{ padding: '4px' }}>
        <span className="text-black-50" style={{ fontSize: '0.75rem' }}>—</span>
      </td>
    )
  }

  const cellStyle = getCellStyle(slot)
  let statusLabel = 'Planeado'
  if (slot.occurrence_status) {
    statusLabel = OCCURRENCE_LABELS[slot.occurrence_status] ?? slot.occurrence_status
  } else if (slot.is_past) {
    statusLabel = 'Pendente'
  }

  const tooltipLines = [
    slot.module  ? `Módulo: ${slot.module.name} (${slot.module.hours_total}h)` : '',
    slot.teacher ? `Professor: ${slot.teacher.name}` : '',
    slot.room    ? `Sala: ${slot.room.name}` : '',
    slot.class_info ? `Turma: ${slot.class_info.name}` : '',
    slot.hours_given == null ? '' : `Horas dadas: ${slot.hours_given}h`,
  ].filter(Boolean)

  return (
    <td title={tooltipLines.join('\n')} style={{ padding: '4px', verticalAlign: 'top' }}>
      <div
        style={{
          ...cellStyle,
          padding: '6px 8px',
          borderRadius: '4px',
          fontSize: '0.78rem',
          minHeight: '60px',
        }}
      >
        <div className="fw-semibold text-truncate" style={{ fontSize: '0.8rem' }}>
          {slot.subject?.name ?? '—'}
        </div>
        <div className="text-muted text-truncate" style={{ fontSize: '0.72rem' }}>
          {slot.teacher?.name ?? ''}
        </div>
        <div className="text-muted text-truncate" style={{ fontSize: '0.72rem' }}>
          {slot.room?.name ?? ''}
        </div>
        <div
          style={{
            fontSize: '0.7rem',
            marginTop: '3px',
            fontWeight: 600,
            opacity: 0.8,
          }}
        >
          {statusLabel}
        </div>
      </div>
    </td>
  )
}

SlotCell.propTypes = {
  slot: PropTypes.shape({
    subject:    PropTypes.shape({ id: PropTypes.number, name: PropTypes.string }),
    teacher:    PropTypes.shape({ name: PropTypes.string }),
    room:       PropTypes.shape({ name: PropTypes.string }),
    class_info: PropTypes.shape({ name: PropTypes.string }),
    module:     PropTypes.shape({ name: PropTypes.string, hours_total: PropTypes.number }),
    occurrence_status: PropTypes.string,
    is_past:    PropTypes.bool,
    hours_given: PropTypes.number,
  }),
}

// ---------------------------------------------------------------------------
// WeekGrid — main component
// ---------------------------------------------------------------------------
const WeekGrid = ({ slots, isLoading, baseTimeslots = [], weekStart = '' }) => {
  const slotMap = useMemo(() => buildSlotMap(slots), [slots])

  const referenceTimeslots = useMemo(() => {
    if (baseTimeslots.length > 0) {
      return baseTimeslots
    }
    return slots.map((s) => s.timeslot)
  }, [baseTimeslots, slots])

  const uniqueTimes = useMemo(
    () => [...new Set(referenceTimeslots.map(t => normalizeTimeLabel(t.start_time)))].sort((a, b) => a.localeCompare(b)),
    [referenceTimeslots],
  )

  const activeDays = useMemo(
    () => [...new Set(referenceTimeslots.map(t => t.day_of_week))].sort((a, b) => a - b),
    [referenceTimeslots],
  )

  // Map start_time → end_time (for the time column)
  const endTimeMap = useMemo(() => {
    const map = {}
    referenceTimeslots.forEach(t => {
      map[normalizeTimeLabel(t.start_time)] = normalizeTimeLabel(t.end_time)
    })
    return map
  }, [referenceTimeslots])

  // Map day_of_week → date string (for column header)
  const dayDateMapFromSlots = useMemo(() => {
    const map = {}
    slots.forEach(s => { map[s.timeslot.day_of_week] = s.date })
    return map
  }, [slots])

  const dayDateMap = useMemo(() => {
    const map = {}
    activeDays.forEach((day) => {
      map[day] = dayDateMapFromSlots[day] ?? getDateForDayFromWeekStart(weekStart, day)
    })
    return map
  }, [activeDays, dayDateMapFromSlots, weekStart])

  if (isLoading) {
    return (
      <div className="text-center p-5 text-muted">
        <CSpinner size="sm" className="me-2" />
        A carregar horário…
      </div>
    )
  }

  if (!slots.length) {
    return (
      <div className="text-center p-5 text-muted" style={{ fontSize: '0.9rem' }}>
        Sem aulas registadas para esta semana e seleção.
      </div>
    )
  }

  return (
    <div className="table-responsive">
      <table
        className="table table-bordered table-sm align-middle mb-0"
        style={{ tableLayout: 'fixed' }}
      >
        <thead className="table-light">
          <tr>
            <th className="text-center align-middle" style={{ width: '96px', fontSize: '0.8rem' }}>Horário</th>
            {activeDays.map(d => (
              <th key={d} className="text-center" style={{ fontSize: '0.8rem' }}>
                <div>{DAY_LABELS[d]}</div>
                <div className="text-muted fw-normal" style={{ fontSize: '0.72rem' }}>
                  {formatDateLabel(dayDateMap[d])}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {uniqueTimes.map(time => (
            <tr key={time}>
              <td
                className="fw-bold text-muted bg-light text-center"
                style={{ fontSize: '0.75rem', whiteSpace: 'nowrap', verticalAlign: 'middle' }}
              >
                {time}
                <br />
                <span className="fw-normal text-black-50">{endTimeMap[time] ?? ''}</span>
              </td>
              {activeDays.map(dayIdx => (
                <SlotCell key={`${dayIdx}:${time}`} slot={slotMap[`${dayIdx}:${time}`] ?? null} />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const slotShape = PropTypes.shape({
  schedule_output_id: PropTypes.number.isRequired,
  date: PropTypes.string,
  timeslot: PropTypes.shape({
    id: PropTypes.number.isRequired,
    day_of_week: PropTypes.number.isRequired,
    start_time: PropTypes.string.isRequired,
    end_time: PropTypes.string.isRequired,
  }).isRequired,
  subject:    PropTypes.shape({ id: PropTypes.number, name: PropTypes.string }),
  teacher:    PropTypes.shape({ id: PropTypes.number, name: PropTypes.string }),
  room:       PropTypes.shape({ id: PropTypes.number, name: PropTypes.string }),
  class_info: PropTypes.shape({ id: PropTypes.number, name: PropTypes.string }),
  module:     PropTypes.shape({ id: PropTypes.number, name: PropTypes.string, hours_total: PropTypes.number }),
  is_past:    PropTypes.bool.isRequired,
  occurrence_status: PropTypes.string,
  hours_given: PropTypes.number,
})

WeekGrid.propTypes = {
  slots:     PropTypes.arrayOf(slotShape).isRequired,
  isLoading: PropTypes.bool,
  weekStart: PropTypes.string,
  baseTimeslots: PropTypes.arrayOf(
    PropTypes.shape({
      day_of_week: PropTypes.number.isRequired,
      start_time: PropTypes.string.isRequired,
      end_time: PropTypes.string.isRequired,
    }),
  ),
}

export default WeekGrid
