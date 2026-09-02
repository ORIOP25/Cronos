import { CFormLabel, CFormInput, CFormFeedback, CRow, CCol, CInputGroup, CInputGroupText } from '@coreui/react'

export function LunchStep({ values, fieldErrors, onChange }) {
  return (
    <div className="foundation-step-lunch">
      <h4 tabIndex="-1" className="h5 mb-3 text-dark fw-bold">6. Período e Duração de Almoço</h4>
      <p className="text-muted small mb-4">
        Configure a janela horária reservada para o almoço de alunos e professores.
      </p>

      <CRow className="g-3">
        <CCol md={6}>
          <CFormLabel htmlFor="lunch_window_start">Início da Janela de Almoço *</CFormLabel>
          <CFormInput
            type="time"
            id="lunch_window_start"
            name="lunch_window_start"
            value={values.lunch_window_start || '12:30'}
            invalid={Boolean(fieldErrors.lunch_window_start)}
            onChange={(e) => onChange('lunch_window_start', e.target.value)}
          />
          {fieldErrors.lunch_window_start && (
            <CFormFeedback invalid>{fieldErrors.lunch_window_start}</CFormFeedback>
          )}
        </CCol>

        <CCol md={6}>
          <CFormLabel htmlFor="lunch_window_end">Fim da Janela de Almoço *</CFormLabel>
          <CFormInput
            type="time"
            id="lunch_window_end"
            name="lunch_window_end"
            value={values.lunch_window_end || '14:00'}
            invalid={Boolean(fieldErrors.lunch_window_end)}
            onChange={(e) => onChange('lunch_window_end', e.target.value)}
          />
          {fieldErrors.lunch_window_end && (
            <CFormFeedback invalid>{fieldErrors.lunch_window_end}</CFormFeedback>
          )}
        </CCol>

        <CCol md={12} className="mt-4">
          <CFormLabel htmlFor="lunch_min_duration_minutes">
            Duração Mínima de Almoço Garantida *
          </CFormLabel>
          <CInputGroup>
            <CFormInput
              type="number"
              id="lunch_min_duration_minutes"
              name="lunch_min_duration_minutes"
              min={1}
              max={180}
              value={values.lunch_min_duration_minutes ?? 60}
              invalid={Boolean(fieldErrors.lunch_min_duration_minutes)}
              aria-describedby="lunch_min_duration_minutes-unit lunch_min_duration_minutes-feedback"
              onChange={(e) => onChange('lunch_min_duration_minutes', Number(e.target.value))}
            />
            <CInputGroupText id="lunch_min_duration_minutes-unit">Minutos</CInputGroupText>
          </CInputGroup>
          <small className="text-muted d-block mt-1">
            Tempo mínimo contínuo que todo o horário terá livre para refeição (omissão: 60 minutos).
          </small>
          {fieldErrors.lunch_min_duration_minutes && (
            <CFormFeedback id="lunch_min_duration_minutes-feedback" className="d-block" invalid>{fieldErrors.lunch_min_duration_minutes}</CFormFeedback>
          )}
        </CCol>
      </CRow>
    </div>
  )
}
