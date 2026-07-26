import { useMemo } from 'react'
import { CSpinner } from '@coreui/react'
import { formatDateShort } from '../utils/formatUtils'
import { getSubjectColor } from '../utils/subjectColors'
import { buildWeekGridModel } from '../utils/weekGridModel'
import { getLessonLogStatus } from '../utils/presentation'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const DAY_LABELS = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']

const OCCURRENCE_CLASSES = {
  GIVEN:       'zen-state-given',
  GAP:         'zen-state-gap',
  SUBSTITUTED: 'zen-state-substituted',
  REVOKED:     'zen-state-planned',
}

const OPEN_OCCURRENCE_CLASS = 'zen-state-open'
const PLANNED_CLASS = 'zen-state-planned'

const OCCURRENCE_LABELS = {
  GIVEN:       'Dada ✓',
  GAP:         'Falta ✗',
  SUBSTITUTED: 'Substituída ↔',
  REVOKED:     'Revertida',
}

// ---------------------------------------------------------------------------
// Pure helpers — outside component (SonarQube S7721)
// ---------------------------------------------------------------------------

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

  // 1. Completed lesson log
  if (slot.lesson_log_status === 'COMPLETED') {
    return {
      className: `zen-state-card ${getLessonLogStatus('COMPLETED').stateClass}`,
      style: { opacity: 0.55, filter: 'grayscale(0.5)' },
    }
  }

  // 2. Teacher registered OCCURRENCE (undecided)
  if (slot.lesson_log_status === 'OCCURRENCE') {
    return {
      className: `zen-state-card ${getLessonLogStatus('OCCURRENCE').stateClass}`,
      style: { opacity: 0.55, filter: 'grayscale(0.5)' },
    }
  }

  // Future/Current slots: Use subject color with opacity
  if (!slot.is_past) {
    return {
      className: 'zen-state-card',
      style: {
        backgroundColor: `${color}26`,
        borderLeftColor: color,
      },
    }
  }

  // Past slots with active (undecided) occurrence
  if (slot.occurrence_id && !slot.occurrence_decided_at) {
    return {
      className: `zen-state-card ${OPEN_OCCURRENCE_CLASS}`,
      style: { opacity: 0.55, filter: 'grayscale(0.5)' },
    }
  }

  // Past slots with decided occurrence
  if (slot.occurrence_status && slot.occurrence_decided_at && OCCURRENCE_CLASSES[slot.occurrence_status]) {
    const cls = OCCURRENCE_CLASSES[slot.occurrence_status]
    if (slot.occurrence_status === 'REVOKED') {
      return {
        className: `zen-state-card ${cls}`,
        style: { opacity: 0.45, filter: 'grayscale(0.6)' },
      }
    }
    return {
      className: `zen-state-card ${cls}`,
      style: { opacity: 0.55, filter: 'grayscale(0.5)' },
    }
  }

  // Past but no occurrence registered yet (Planned/Pending)
  return {
    className: `zen-state-card ${PLANNED_CLASS}`,
    style: { borderLeftColor: color },
  }
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

  // V4.1: All slots with valid context are clickable.
  // The LessonLogModal handles read-only/edit mode based on slot state.
  const canOpenOperationalAction = Boolean(
    isOperationalEnabled
    && !hasCollision
    && (slot.active_schedule_block_id || slot.operational_block_id)
    && slot.date
    && typeof onOpenOperationalAction === 'function'
  )

  let operationalBlockReason = ''
  if (isOperationalEnabled && !canOpenOperationalAction && !isWeekLocked) {
    if (hasCollision) {
      operationalBlockReason = 'Conflito no slot. Use a página de Faltas para análise.'
    } else if (!(slot.active_schedule_block_id || slot.operational_block_id) || !slot.date) {
      operationalBlockReason = 'Este bloco não tem contexto operacional completo.'
    }
  }

  const { className: cellClassName, style: cellStyle } = getCellVisuals(slot)
  const isSubstituteBlock = slot.is_substituted_block === true
  let statusLabel = getLessonLogStatus(slot.lesson_log_status).label
  if (isSubstituteBlock) {
    statusLabel = 'Substituição'
  } else if (slot.lesson_log_status === 'COMPLETED') {
    statusLabel = getLessonLogStatus('COMPLETED').label
  } else if (slot.lesson_log_status === 'OCCURRENCE') {
    statusLabel = getLessonLogStatus('OCCURRENCE').label
  } else if (slot.occurrence_status && slot.occurrence_decided_at) {
    statusLabel = OCCURRENCE_LABELS[slot.occurrence_status] ?? slot.occurrence_status
  } else if (slot.occurrence_id && !slot.occurrence_decided_at) {
    statusLabel = 'Ocorrência'
  } else if (slot.is_past) {
    statusLabel = slot.class_info?.name || null
  }

  const titleText = buildCellTitle(slotEntries)

  const handleOpenOperationalAction = () => {
    if (!canOpenOperationalAction) {
      return
    }
    onOpenOperationalAction({
      ...slot,
      can_create_occurrence: canCreateOccurrence,
      can_decide_occurrence: canDecideOccurrence,
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
          {isWeekLocked ? 'Consultar' : 'Registar'}
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
  const { slotMap, uniqueTimes, activeDays, endTimeMap, dayDateMap } = useMemo(
    () => buildWeekGridModel(slots, baseTimeslots, weekStart),
    [slots, baseTimeslots, weekStart],
  )

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
                aria-label={`${DAY_LABELS[d]} ${formatDateShort(dayDateMap[d])}`}
              >
                <div>{DAY_LABELS[d]}</div>
                <div className="text-muted fw-normal" style={{ fontSize: '0.72rem' }}>
                  {formatDateShort(dayDateMap[d])}
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

export default WeekGrid
