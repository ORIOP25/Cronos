import { CFormLabel, CFormInput, CFormFeedback, CInputGroup, CInputGroupText } from '@coreui/react'
import {
  buildDailyTimeline,
  normalizeBreakOverrides,
  removeBreakOverride,
  setBreakOverride,
  validateBreakOverrides,
} from './breakTimeline'

const INVALID_REASON_MESSAGES = {
  position: 'A posição do ajuste é inválida.',
  duplicate: 'Existe mais de um ajuste para esta aula.',
  duration: 'A duração do ajuste deve estar entre 0 e 60 minutos.',
}

export function BreakTimelineEditor({
  values,
  fieldErrors = {},
  onChange,
  title,
  description,
  showUsualBreak = true,
  usualBreakLabel = 'Duração do Intervalo *',
  usualBreakInputId = 'break_duration_minutes',
}) {
  const timeline = buildDailyTimeline(values)
  const usualBreak = Number(values.break_duration_minutes ?? 10)
  const overrides = normalizeBreakOverrides(values.break_overrides)
  const liveError = validateBreakOverrides(values)
  const overrideError = fieldErrors.break_overrides || liveError

  const setOverride = (afterSlot, durationMinutes) => {
    onChange(
      'break_overrides',
      setBreakOverride(values.break_overrides, afterSlot, durationMinutes, usualBreak),
    )
  }

  const resetOverride = (afterSlot) => {
    onChange('break_overrides', removeBreakOverride(values.break_overrides, afterSlot))
  }

  const orphanOverrides = timeline?.unusedOverrides ?? []
  const invalidOverrides = timeline?.invalidOverrides ?? []

  return (
    <div className="foundation-step-break-duration">
      {title && <h4 tabIndex="-1" className="h5 mb-3 text-dark fw-bold">{title}</h4>}
      {description && <p className="text-muted small mb-4">{description}</p>}

      {showUsualBreak && (
        <div className="mb-3" style={{ maxWidth: '400px' }}>
          <CFormLabel htmlFor={usualBreakInputId}>{usualBreakLabel}</CFormLabel>
          <CInputGroup>
            <CFormInput
              type="number"
              id={usualBreakInputId}
              name={usualBreakInputId}
              min={0}
              max={60}
              value={values.break_duration_minutes ?? 10}
              invalid={Boolean(fieldErrors.break_duration_minutes)}
              aria-describedby={`${usualBreakInputId}-unit ${usualBreakInputId}-feedback`}
              onChange={(e) => onChange('break_duration_minutes', Number(e.target.value))}
            />
            <CInputGroupText id={`${usualBreakInputId}-unit`}>Minutos</CInputGroupText>
          </CInputGroup>
          {fieldErrors.break_duration_minutes && (
            <CFormFeedback id={`${usualBreakInputId}-feedback`} className="d-block" invalid>{fieldErrors.break_duration_minutes}</CFormFeedback>
          )}
        </div>
      )}

      {timeline && timeline.slots.length > 1 && (
        <div className="mt-4" style={{ maxWidth: '480px' }}>
          <h6 className="fw-bold text-secondary mb-2">Pausas entre as aulas do dia</h6>
          <p className="text-muted small mb-3">
            Cada aula pode ter uma pausa diferente. &quot;Repor padrão&quot; volta à duração habitual.
          </p>
          <div className="d-flex flex-column gap-3">
            {timeline.slots.slice(0, -1).map((slot) => {
              const nextSlot = timeline.slots[slot.index]
              const hasOverride = overrides.some((override) => override.after_slot === slot.index)
              return (
                <div key={slot.id}>
                  <CFormLabel htmlFor={`break_after_slot_${slot.index}`}>
                    Pausa após a aula {slot.index} ({slot.start}-{slot.end})
                  </CFormLabel>
                  <CInputGroup>
                    <CFormInput
                      type="number"
                      inputMode="numeric"
                      id={`break_after_slot_${slot.index}`}
                      name={`break_after_slot_${slot.index}`}
                      min={0}
                      max={60}
                      value={Number.isFinite(slot.breakAfter) ? slot.breakAfter : usualBreak}
                      onChange={(e) => setOverride(slot.index, Number(e.target.value))}
                    />
                    <CInputGroupText>Minutos</CInputGroupText>
                  </CInputGroup>
                  <div className="d-flex justify-content-between align-items-center mt-1">
                    <span className="text-muted small">
                      Segue-se a aula {slot.index + 1} às {nextSlot.start}
                    </span>
                    {hasOverride && (
                      <button
                        type="button"
                        className="btn btn-link btn-sm p-0"
                        aria-label={`Repor padrão após a aula ${slot.index}`}
                        onClick={() => setOverride(slot.index, usualBreak)}
                      >
                        Repor padrão
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {(orphanOverrides.length > 0 || invalidOverrides.length > 0) && (
        <div className="mt-4" style={{ maxWidth: '480px' }}>
          <h6 className="fw-bold text-secondary mb-2">Ajustes por usar</h6>
          <div className="d-flex flex-column gap-2">
            {orphanOverrides.map((position) => (
              <div key={`orphan-${position}`} className="d-flex justify-content-between align-items-center">
                <span className="text-muted small">
                  Ajuste após a aula {position} (sem aula seguinte)
                </span>
                <button
                  type="button"
                  className="btn btn-link btn-sm p-0"
                  aria-label={`Remover ajuste após a aula ${position}`}
                  onClick={() => resetOverride(position)}
                >
                  Remover ajuste
                </button>
              </div>
            ))}
            {invalidOverrides.map((override, index) => (
              <div key={`invalid-${index}`} className="d-flex justify-content-between align-items-center">
                <span className="text-muted small">
                  Ajuste inválido{Number.isInteger(override.after_slot) ? ` após a aula ${override.after_slot}` : ''}: {INVALID_REASON_MESSAGES[override.reason]}
                </span>
                {Number.isInteger(override.after_slot) && (
                  <button
                    type="button"
                    className="btn btn-link btn-sm p-0"
                    aria-label={`Remover ajuste após a aula ${override.after_slot}`}
                    onClick={() => resetOverride(override.after_slot)}
                  >
                    Remover ajuste
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {overrideError && (
        <div className="alert alert-danger mt-3" role="alert">{overrideError}</div>
      )}
    </div>
  )
}
