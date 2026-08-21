import { CFormLabel, CFormInput, CFormFeedback } from '@coreui/react'

export function SlotDurationStep({ values, fieldErrors, onChange }) {
  return (
    <div className="foundation-step-slot-duration">
      <h4 className="h5 mb-3 text-dark fw-bold">4. Duração dos Blocos de Aulas</h4>
      <p className="text-muted small mb-4">
        Indique a duração padrão de cada tempo letivo (normalmente 45, 50 ou 90 minutos).
      </p>

      <div className="mb-3" style={{ maxWidth: '400px' }}>
        <CFormLabel htmlFor="slot_duration_minutes">Duração do Bloco (Minutos) *</CFormLabel>
        <CFormInput
          type="number"
          id="slot_duration_minutes"
          name="slot_duration_minutes"
          min={15}
          max={120}
          value={values.slot_duration_minutes ?? 50}
          invalid={Boolean(fieldErrors.slot_duration_minutes)}
          onChange={(e) => onChange('slot_duration_minutes', Number(e.target.value))}
        />
        <small className="text-muted d-block mt-1">
          Valor recomendado pelo sistema: 50 minutos.
        </small>
        {fieldErrors.slot_duration_minutes && (
          <CFormFeedback invalid>{fieldErrors.slot_duration_minutes}</CFormFeedback>
        )}
      </div>
    </div>
  )
}
