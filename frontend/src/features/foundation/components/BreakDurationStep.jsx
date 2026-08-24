import { CFormLabel, CFormInput, CFormFeedback } from '@coreui/react'

export function BreakDurationStep({ values, fieldErrors, onChange }) {
  return (
    <div className="foundation-step-break-duration">
      <h4 tabIndex="-1" className="h5 mb-3 text-dark fw-bold">5. Intervalos entre Blocos</h4>
      <p className="text-muted small mb-4">
        Indique a duração padrão dos intervalos entre blocos de aulas consecutivos.
      </p>

      <div className="mb-3" style={{ maxWidth: '400px' }}>
        <CFormLabel htmlFor="break_duration_minutes">Duração do Intervalo (Minutos) *</CFormLabel>
        <CFormInput
          type="number"
          id="break_duration_minutes"
          name="break_duration_minutes"
          min={0}
          max={60}
          value={values.break_duration_minutes ?? 10}
          invalid={Boolean(fieldErrors.break_duration_minutes)}
          onChange={(e) => onChange('break_duration_minutes', Number(e.target.value))}
        />
        <small className="text-muted d-block mt-1">
          Valor recomendado pelo sistema: 10 minutos (0 minutos se não houver intervalo obrigatório entre tempos).
        </small>
        {fieldErrors.break_duration_minutes && (
          <CFormFeedback invalid>{fieldErrors.break_duration_minutes}</CFormFeedback>
        )}
      </div>
    </div>
  )
}
