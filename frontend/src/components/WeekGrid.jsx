import { useMemo } from 'react'
import StatePanel from './StatePanel'
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
      className: `zen-state-card ${getLessonLogStatus('COMPLETED').stateClass} is-muted`,
      style: {},
    }
  }

  // 2. Teacher registered OCCURRENCE (undecided)
  if (slot.lesson_log_status === 'OCCURRENCE') {
    return {
      className: `zen-state-card ${getLessonLogStatus('OCCURRENCE').stateClass} is-muted`,
      style: {},
    }
  }

  // Future/Current slots: Use subject color with opacity
  if (!slot.is_past) {
    return {
      className: 'zen-state-card',
      style: { '--slot-color': color },
    }
  }

  // Past slots with active (undecided) occurrence
  if (slot.occurrence_id && !slot.occurrence_decided_at) {
    return {
      className: `zen-state-card ${OPEN_OCCURRENCE_CLASS} is-muted`,
      style: {},
    }
  }

  // Past slots with decided occurrence
  if (slot.occurrence_status && slot.occurrence_decided_at && OCCURRENCE_CLASSES[slot.occurrence_status]) {
    const cls = OCCURRENCE_CLASSES[slot.occurrence_status]
    if (slot.occurrence_status === 'REVOKED') {
      return {
        className: `zen-state-card ${cls} is-revoked`,
        style: {},
      }
    }
    return {
      className: `zen-state-card ${cls} is-muted`,
      style: {},
    }
  }

  // Past but no occurrence registered yet (Planned/Pending)
  return {
    className: `zen-state-card ${PLANNED_CLASS}`,
    style: { '--slot-color': color },
  }
}

// ---------------------------------------------------------------------------
// SlotCell — individual table cell
// ---------------------------------------------------------------------------
const SlotCell = ({ slotEntries, isOperationalEnabled, onOpenOperationalAction }) => {
  if (!slotEntries || slotEntries.length === 0) {
    return (
      <td className="week-grid__cell week-grid__empty">
        <span>—</span>
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
  let statusLabel = null
  if (isSubstituteBlock) {
    statusLabel = 'Substituição'
  } else if (slot.lesson_log_status === 'COMPLETED') {
    statusLabel = 'Concluído'
  } else if (slot.lesson_log_status === 'OCCURRENCE') {
    statusLabel = getLessonLogStatus('OCCURRENCE').label
  } else if (slot.occurrence_status && slot.occurrence_decided_at) {
    statusLabel = OCCURRENCE_LABELS[slot.occurrence_status] ?? slot.occurrence_status
  } else if (slot.occurrence_id && !slot.occurrence_decided_at) {
    statusLabel = 'Ocorrência'
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
        className={`${cellClassName} week-grid__card${isWeekLocked ? ' is-locked' : ''}${isDraft ? ' is-draft' : ''}`}
        style={cellStyle}
      >
      <div className="week-grid__subject">
        {slot.subject?.name ?? '—'}
      </div>
      <div className="week-grid__details">
        <span className="week-grid__secondary">
          {[slot.teacher?.name, slot.room?.name].filter(Boolean).join(' · ')}
        </span>
        {statusLabel ? (
          <span className={`week-grid__action${slot.lesson_log_status === 'COMPLETED' ? ' week-grid__action--completed' : ''}`}>
            {statusLabel}
          </span>
        ) : canOpenOperationalAction ? (
          <span className="week-grid__action">
            {isWeekLocked ? 'Consultar' : 'Registar'}
          </span>
        ) : null}
      </div>
      {hasCollision ? (
        <div className="badge text-bg-danger mt-1">
          Conflito x{slotEntries.length}
        </div>
      ) : null}
      {isDraft ? (
        <div className="badge text-bg-secondary mt-1">
          Rascunho
        </div>
      ) : null}
      {!canOpenOperationalAction && operationalBlockReason ? (
        <div className="week-grid__secondary">
          {operationalBlockReason}
        </div>
      ) : null}
    </div>
  )

  const ariaLabel = slot
    ? `${slot.subject?.name ?? 'Sem disciplina'}, ${slot.teacher?.name ?? ''}, ${slot.room?.name ?? ''}, ${statusLabel ?? 'Planeado'}`
    : 'Célula vazia'

  return (
    <td
      title={titleText}
      className="week-grid__cell"
      role="gridcell"
      aria-label={ariaLabel}
    >
      <button
        type="button"
        onClick={handleOpenOperationalAction}
        disabled={!canOpenOperationalAction}
        className="week-grid__button"
        aria-label={canOpenOperationalAction ? `Abrir registo de ${slot.subject?.name ?? 'aula'}` : undefined}
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
  fitViewport = false,
}) => {
  const { slotMap, uniqueTimes, activeDays, endTimeMap, dayDateMap } = useMemo(
    () => buildWeekGridModel(slots, baseTimeslots, weekStart),
    [slots, baseTimeslots, weekStart],
  )

  if (isLoading) {
    return <StatePanel state="loading" title="A carregar o horário" description="Estamos a preparar os blocos desta semana." />
  }

  if (!slots.length) {
    return <StatePanel state="empty" title="Sem aulas nesta seleção" description="Escolha outra turma, professor ou semana para consultar o horário." />
  }

  return (
    <div className="week-grid-scroll" tabIndex="0" role="region" aria-label="Grelha semanal de horários. Use Shift e roda do rato para deslocar horizontalmente.">
      <table
        className={`week-grid${fitViewport ? ' week-grid--fit-viewport' : ''}`}
        style={{
          '--week-grid-min-width': `${76 + activeDays.length * 132}px`,
          '--week-grid-row-count': Math.max(uniqueTimes.length, 1),
        }}
        aria-label="Grelha semanal de horários"
      >
        <thead>
          <tr>
            <th
              className="week-grid__time-header"
              scope="col"
            >
              Horário
            </th>
            {activeDays.map(d => (
              <th
                key={d}
                className="week-grid__day-header"
                scope="col"
                aria-label={`${DAY_LABELS[d]} ${formatDateShort(dayDateMap[d])}`}
              >
                <div>{DAY_LABELS[d]}</div>
                <div className="fw-normal" style={{ fontSize: '0.72rem' }}>
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
                className="week-grid__time"
                scope="row"
                aria-label={`${time} – ${endTimeMap[time] ?? ''}`}
              >
                <span className="week-grid__time-start">{time}</span>
                <span className="week-grid__time-end">{endTimeMap[time] ?? ''}</span>
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
