import React, { useMemo } from 'react'
import PropTypes from 'prop-types'
import { CSpinner } from '@coreui/react'
import { getSubjectColor } from '../utils/subjectColors'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const DAY_LABELS = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']

const OCCURRENCE_CLASSES = {
  GIVEN:       'zen-state-given',
  GAP:         'zen-state-gap',
  SUBSTITUTED: 'zen-state-substituted',
}

const OPEN_OCCURRENCE_CLASS = 'zen-state-open'
const PLANNED_CLASS = 'zen-state-planned'

const OCCURRENCE_LABELS = {
  GIVEN:       'Dada ✓',
  GAP:         'Furo ✗',
  SUBSTITUTED: 'Substituída ↔',
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

/** Build a lookup map: "dayOfWeek:startTime" → [slots]. */
function buildSlotMap(slots) {
  const map = {}
  slots.forEach(slot => {
    const key = `${slot.timeslot.day_of_week}:${normalizeTimeLabel(slot.timeslot.start_time)}`
    if (!map[key]) {
      map[key] = []
    }
    map[key].push(slot)
  })
  return map
}

function buildTooltipLines(slot) {
  return [
    slot.module ? `Modulo: ${slot.module.name} (${slot.module.hours_total}h)` : '',
    slot.teacher ? `Professor: ${slot.teacher.name}` : '',
    slot.room ? `Sala: ${slot.room.name}` : '',
    slot.class_info ? `Turma: ${slot.class_info.name}` : '',
    slot.hours_given == null ? '' : `Horas dadas: ${slot.hours_given}h`,
  ].filter(Boolean)
}

function buildCellTitle(slotEntries) {
  if (slotEntries.length <= 1) {
    return buildTooltipLines(slotEntries[0]).join('\n')
  }

  const sections = slotEntries.map((entry, idx) => {
    const lessonLabel = entry.subject?.name ?? `Aula ${idx + 1}`
    const details = buildTooltipLines(entry)
    return [`[${idx + 1}] ${lessonLabel}`, ...details].join('\n')
  })
  return sections.join('\n\n')
}

/** Compute the CSS class and style for a cell based on occurrence status. */
function getCellVisuals(slot) {
  if (!slot) return { className: '', style: {} }
  const color = getSubjectColor(slot.subject?.id ?? 0)

  // 1. If it has a completed lesson log:
  if (slot.lesson_log_status === 'COMPLETED') {
    return { className: `zen-state-card zen-state-given`, style: {} }
  }

  // 2. If the teacher registered a self-absence (OCCURRENCE via LessonLog):
  if (slot.lesson_log_status === 'OCCURRENCE') {
    return { className: `zen-state-card zen-state-gap`, style: {} }
  }

  // Future/Current slots: Use subject color with opacity
  if (!slot.is_past) {
    return {
      className: 'zen-state-card',
      style: {
        backgroundColor: `${color}26`, // ~15% opacity
        borderLeftColor: color,
      },
    }
  }

  // Past slots with active (undecided) occurrence
  if (slot.occurrence_id && !slot.occurrence_decided_at) {
    return { className: `zen-state-card ${OPEN_OCCURRENCE_CLASS}`, style: {} }
  }

  // Past slots with decided occurrence
  if (slot.occurrence_status && slot.occurrence_decided_at && OCCURRENCE_CLASSES[slot.occurrence_status]) {
    const cls = OCCURRENCE_CLASSES[slot.occurrence_status]
    // WBS V3 Fase 4: original substituted block gets grayed out
    if (slot.occurrence_status === 'SUBSTITUTED') {
      return {
        className: `zen-state-card ${cls}`,
        style: { opacity: 0.45, filter: 'grayscale(0.6)' },
      }
    }
    return { className: `zen-state-card ${cls}`, style: {} }
  }

  // Past but no occurrence registered yet (Planned/Pending)
  return {
    className: `zen-state-card ${PLANNED_CLASS}`,
    style: { borderLeftColor: color },
  }
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
const SlotCell = ({ slotEntries, isOperationalEnabled, onOpenOperationalAction }) => {
  if (!slotEntries || slotEntries.length === 0) {
    return (
      <td className="bg-light text-center align-middle" style={{ padding: '4px' }}>
        <span className="text-black-50" style={{ fontSize: '0.75rem' }}>—</span>
      </td>
    )
  }

  const slot = slotEntries[0]
  const hasCollision = slotEntries.length > 1
  const canCreateOccurrence = slot.can_create_occurrence !== false
  const canDecideOccurrence = Boolean(slot.can_decide_occurrence)

  const isWeekLocked = slot.week_timesheet_status === 'SUBMITTED' || slot.week_timesheet_status === 'APPROVED'

  const canOpenOperationalAction = Boolean(
    isOperationalEnabled
    && !hasCollision
    && slot.schedule_output_id
    && slot.date
    && !slot.is_substituted_block
    && typeof onOpenOperationalAction === 'function'
    && ((canCreateOccurrence || canDecideOccurrence) || isWeekLocked)
  )

  let operationalBlockReason = ''
  if (isOperationalEnabled && !canOpenOperationalAction && !isWeekLocked) {
    if (hasCollision) {
      operationalBlockReason = 'Conflito no slot. Use a página de Faltas para análise.'
    } else if (!slot.schedule_output_id || !slot.date) {
      operationalBlockReason = 'Este bloco não tem contexto operacional completo.'
    } else if (!(canCreateOccurrence || canDecideOccurrence)) {
      if (slot.occurrence_id && slot.occurrence_decided_at) {
        operationalBlockReason = 'Ocorrência já fechada.'
      } else {
        operationalBlockReason = 'Sem ação operacional disponível para este bloco.'
      }
    }
  }

  const { className: cellClassName, style: cellStyle } = getCellVisuals(slot)
  let statusLabel = 'Planeado'
  if (slot.is_substituted_block) {
    statusLabel = 'Substituição'
  } else if (slot.lesson_log_status === 'COMPLETED') {
    statusLabel = 'Concluída ✓'
  } else if (slot.lesson_log_status === 'OCCURRENCE') {
    statusLabel = 'Falta ✗'
  } else if (slot.occurrence_id && !slot.occurrence_decided_at) {
    statusLabel = 'Pendente de decisão'
  } else if (slot.occurrence_status) {
    statusLabel = OCCURRENCE_LABELS[slot.occurrence_status] ?? slot.occurrence_status
  } else if (slot.is_past) {
    statusLabel = 'Pendente'
  }

  const titleText = buildCellTitle(slotEntries)

  const handleOpenOperationalAction = () => {
    if (!canOpenOperationalAction) {
      return
    }
    onOpenOperationalAction({
      schedule_output_id: slot.schedule_output_id,
      date: slot.date,
      is_past: slot.is_past,
      occurrence_id: slot.occurrence_id,
      occurrence_decided_at: slot.occurrence_decided_at,
      can_create_occurrence: canCreateOccurrence,
      can_decide_occurrence: canDecideOccurrence,
      timeslot: slot.timeslot,
      subject: slot.subject,
      teacher: slot.teacher,
      room: slot.room,
      class_info: slot.class_info,
      occurrence_status: slot.occurrence_status,
      hours_given: slot.hours_given,
      lesson_log_id: slot.lesson_log_id,
      lesson_log_status: slot.lesson_log_status,
      lesson_log_summary: slot.lesson_log_summary,
      lesson_log_notes: slot.lesson_log_notes,
      // WBS Fase 6: campos de fecho semanal
      week_timesheet_status: slot.week_timesheet_status,
      timesheet_id: slot.timesheet_id,
    })
  }

  const isDraft = slot.is_draft === true

  const cardContent = (
    <div
      className={cellClassName}
      style={{
        ...cellStyle,
        fontSize: '0.78rem',
        minHeight: '60px',
        ...(isWeekLocked ? { opacity: 0.55, filter: 'grayscale(0.5)' } : {}),
        ...(isDraft ? { borderStyle: 'dashed', borderWidth: '2px', borderColor: 'var(--cui-secondary)' } : {}),
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
      {hasCollision ? (
        <div className="badge text-bg-danger mt-1" style={{ fontSize: '0.66rem' }}>
          Conflito x{slotEntries.length}
        </div>
      ) : null}
      {isDraft ? (
        <div className="badge text-bg-secondary mt-1" style={{ fontSize: '0.66rem' }}>
          Rascunho
        </div>
      ) : null}
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
      {canOpenOperationalAction ? (
        <div
          className="mt-1 fw-semibold"
          style={{
            fontSize: '0.68rem',
            color: isWeekLocked ? 'var(--cui-secondary)' : 'var(--cui-primary)',
          }}
        >
          {isWeekLocked
            ? 'Consultar'
            : slot.lesson_log_status === 'COMPLETED' || slot.lesson_log_status === 'OCCURRENCE' || slot.occurrence_decided_at
              ? 'Gerir'
              : 'Registar'}
        </div>
      ) : null}
      {!canOpenOperationalAction && operationalBlockReason ? (
        <div className="mt-1 text-muted" style={{ fontSize: '0.66rem' }}>
          {operationalBlockReason}
        </div>
      ) : null}
    </div>
  )

  const ariaLabel = slot
    ? `${slot.subject?.name ?? 'Sem disciplina'}, ${slot.teacher?.name ?? ''}, ${slot.room?.name ?? ''}, ${statusLabel}`
    : 'Célula vazia'

  return (
    <td
      title={titleText}
      style={{ padding: '4px', verticalAlign: 'top' }}
      role="gridcell"
      aria-label={ariaLabel}
    >
      <button
        type="button"
        onClick={handleOpenOperationalAction}
        disabled={!canOpenOperationalAction}
        className="w-100 text-start"
        aria-label={canOpenOperationalAction ? `Abrir registo de ${slot.subject?.name ?? 'aula'}` : undefined}
        style={{
          border: 'none',
          background: 'transparent',
          padding: 0,
          cursor: canOpenOperationalAction ? 'pointer' : 'default',
        }}
      >
        {cardContent}
      </button>
    </td>
  )
}

SlotCell.propTypes = {
  slotEntries: PropTypes.arrayOf(
    PropTypes.shape({
      subject: PropTypes.shape({ id: PropTypes.number, name: PropTypes.string }),
      teacher: PropTypes.shape({ name: PropTypes.string }),
      room: PropTypes.shape({ name: PropTypes.string }),
      class_info: PropTypes.shape({ name: PropTypes.string }),
      module: PropTypes.shape({ name: PropTypes.string, hours_total: PropTypes.number }),
      schedule_output_id: PropTypes.number,
      date: PropTypes.string,
      occurrence_id: PropTypes.number,
      can_create_occurrence: PropTypes.bool,
      can_decide_occurrence: PropTypes.bool,
      occurrence_status: PropTypes.string,
      occurrence_decided_at: PropTypes.string,
      is_past: PropTypes.bool,
      hours_given: PropTypes.number,
    }),
  ),
  isOperationalEnabled: PropTypes.bool,
  onOpenOperationalAction: PropTypes.func,
}

// ---------------------------------------------------------------------------
// WeekGrid — main component
// ---------------------------------------------------------------------------
const WeekGrid = ({
  slots,
  isLoading,
  baseTimeslots = [],
  weekStart = '',
  isOperationalEnabled = false,
  onOpenOperationalAction,
}) => {
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
        role="grid"
        aria-label="Grelha semanal de horários"
      >
        <thead className="table-light">
          <tr>
            <th
              className="text-center align-middle"
              style={{ width: '96px', fontSize: '0.8rem' }}
              scope="col"
            >
              Horário
            </th>
            {activeDays.map(d => (
              <th
                key={d}
                className="text-center"
                style={{ fontSize: '0.8rem' }}
                scope="col"
                aria-label={`${DAY_LABELS[d]} ${formatDateLabel(dayDateMap[d])}`}
              >
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
                scope="row"
                aria-label={`${time} – ${endTimeMap[time] ?? ''}`}
              >
                {time}
                <br />
                <span className="fw-normal text-black-50">{endTimeMap[time] ?? ''}</span>
              </td>
              {activeDays.map(dayIdx => (
                <SlotCell
                  key={`${dayIdx}:${time}`}
                  slotEntries={slotMap[`${dayIdx}:${time}`] ?? []}
                  isOperationalEnabled={isOperationalEnabled}
                  onOpenOperationalAction={onOpenOperationalAction}
                />
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
  occurrence_id: PropTypes.number,
  can_create_occurrence: PropTypes.bool,
  can_decide_occurrence: PropTypes.bool,
  occurrence_status: PropTypes.string,
  hours_given: PropTypes.number,
})

WeekGrid.propTypes = {
  slots:     PropTypes.arrayOf(slotShape).isRequired,
  isLoading: PropTypes.bool,
  weekStart: PropTypes.string,
  isOperationalEnabled: PropTypes.bool,
  onOpenOperationalAction: PropTypes.func,
  baseTimeslots: PropTypes.arrayOf(
    PropTypes.shape({
      day_of_week: PropTypes.number.isRequired,
      start_time: PropTypes.string.isRequired,
      end_time: PropTypes.string.isRequired,
    }),
  ),
}

export default WeekGrid
