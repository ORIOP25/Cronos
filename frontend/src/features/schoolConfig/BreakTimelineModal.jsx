import { useState } from 'react'
import {
  CButton,
  CFormInput,
  CModal,
  CModalBody,
  CModalFooter,
  CModalHeader,
  CModalTitle,
  CTable,
  CTableBody,
  CTableDataCell,
  CTableHead,
  CTableHeaderCell,
  CTableRow,
} from '@coreui/react'
import {
  buildDailyTimeline,
  normalizeBreakOverrides,
  removeBreakOverride,
  setBreakOverride,
  validateBreakOverrides,
} from '../timetable/breakTimeline'

const INVALID_REASON_MESSAGES = {
  position: 'A posição do ajuste é inválida.',
  duplicate: 'Existe mais de um ajuste para esta aula.',
  duration: 'A duração do ajuste deve estar entre 0 e 60 minutos.',
}

export function BreakTimelineModal({ values, onClose, onApply }) {
  const [draft, setDraft] = useState(() => (
    Array.isArray(values.break_overrides)
      ? values.break_overrides.map((entry) => ({ ...entry }))
      : []
  ))
  const [error, setError] = useState('')

  const usualBreak = Number(values.break_duration_minutes ?? 10)
  const draftValues = { ...values, break_overrides: draft }
  const timeline = buildDailyTimeline(draftValues)
  const overrides = normalizeBreakOverrides(draft)
  const hasOverride = (afterSlot) => overrides.some((override) => override.after_slot === afterSlot)

  const updateDuration = (afterSlot, durationMinutes) => {
    setError('')
    setDraft((current) => setBreakOverride(current, afterSlot, durationMinutes, usualBreak))
  }

  const removeOverride = (afterSlot) => {
    setError('')
    setDraft((current) => removeBreakOverride(current, afterSlot))
  }

  const handleApply = () => {
    const validationError = validateBreakOverrides(draftValues)
    if (validationError) {
      setError(validationError)
      return
    }
    onApply(draft)
  }

  const orphanOverrides = timeline?.unusedOverrides ?? []
  const invalidOverrides = timeline?.invalidOverrides ?? []

  return (
    <CModal visible onClose={onClose} size="lg" scrollable>
      <CModalHeader>
        <CModalTitle>Personalizar intervalos</CModalTitle>
      </CModalHeader>
      <CModalBody>
        <p className="text-muted small mb-3">
          Cada aula pode ter uma pausa diferente. As alterações passam para o formulário apenas
          quando escolher <strong>Aplicar ao formulário</strong>.
        </p>

        {timeline && timeline.slots.length > 1 ? (
          <CTable responsive align="middle" className="mb-0">
            <CTableHead>
              <CTableRow>
                <CTableHeaderCell>Pausa depois da aula</CTableHeaderCell>
                <CTableHeaderCell>Duração</CTableHeaderCell>
                <CTableHeaderCell>Aula seguinte</CTableHeaderCell>
                <CTableHeaderCell className="text-end">Ação</CTableHeaderCell>
              </CTableRow>
            </CTableHead>
            <CTableBody>
              {timeline.slots.slice(0, -1).map((slot) => {
                const nextSlot = timeline.slots[slot.index]
                return (
                  <CTableRow key={slot.id}>
                    <CTableDataCell className="text-nowrap">
                      Aula {slot.index} ({slot.start}-{slot.end})
                    </CTableDataCell>
                    <CTableDataCell>
                      <CFormInput
                        type="number"
                        inputMode="numeric"
                        size="sm"
                        min={0}
                        max={60}
                        aria-label={`Pausa após a aula ${slot.index} (${slot.start}-${slot.end})`}
                        value={Number.isFinite(slot.breakAfter) ? slot.breakAfter : usualBreak}
                        onChange={(event) => updateDuration(slot.index, Number(event.target.value))}
                        style={{ maxWidth: '6rem' }}
                      />
                    </CTableDataCell>
                    <CTableDataCell className="text-nowrap">
                      Aula {slot.index + 1} às {nextSlot.start}
                    </CTableDataCell>
                    <CTableDataCell className="text-end">
                      {hasOverride(slot.index) && (
                        <CButton
                          type="button"
                          color="link"
                          size="sm"
                          className="p-0 text-nowrap"
                          aria-label={`Repor padrão após a aula ${slot.index}`}
                          onClick={() => updateDuration(slot.index, usualBreak)}
                        >
                          Repor padrão
                        </CButton>
                      )}
                    </CTableDataCell>
                  </CTableRow>
                )
              })}
            </CTableBody>
          </CTable>
        ) : (
          <p className="text-muted mb-0">A grelha atual não permite calcular pausas entre aulas.</p>
        )}

        {(orphanOverrides.length > 0 || invalidOverrides.length > 0) && (
          <div className="mt-4">
            <h6 className="fw-bold text-secondary mb-2">Ajustes por usar</h6>
            <div className="d-flex flex-column gap-2">
              {orphanOverrides.map((position) => (
                <div key={`orphan-${position}`} className="d-flex justify-content-between align-items-center gap-3">
                  <span className="text-muted small">
                    Ajuste após a aula {position} (sem aula seguinte)
                  </span>
                  <CButton
                    type="button"
                    color="link"
                    size="sm"
                    className="p-0 text-nowrap"
                    aria-label={`Remover ajuste após a aula ${position}`}
                    onClick={() => removeOverride(position)}
                  >
                    Remover ajuste
                  </CButton>
                </div>
              ))}
              {invalidOverrides.map((override, index) => (
                <div key={`invalid-${index}`} className="d-flex justify-content-between align-items-center gap-3">
                  <span className="text-muted small">
                    Ajuste inválido{Number.isInteger(override.after_slot) ? ` após a aula ${override.after_slot}` : ''}: {INVALID_REASON_MESSAGES[override.reason]}
                  </span>
                  {Number.isInteger(override.after_slot) && (
                    <CButton
                      type="button"
                      color="link"
                      size="sm"
                      className="p-0 text-nowrap"
                      aria-label={`Remover ajuste após a aula ${override.after_slot}`}
                      onClick={() => removeOverride(override.after_slot)}
                    >
                      Remover ajuste
                    </CButton>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {error && <div className="alert alert-danger mt-3" role="alert">{error}</div>}
      </CModalBody>
      <CModalFooter>
        <CButton type="button" color="secondary" variant="outline" onClick={onClose}>
          Cancelar
        </CButton>
        <CButton type="button" color="primary" onClick={handleApply}>
          Aplicar ao formulário
        </CButton>
      </CModalFooter>
    </CModal>
  )
}
