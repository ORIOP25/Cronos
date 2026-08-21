import { CFormLabel, CFormInput, CFormFeedback, CRow, CCol } from '@coreui/react'

export function OpeningStep({ values, fieldErrors, onChange }) {
  return (
    <div className="foundation-step-opening">
      <h4 className="h5 mb-3 text-dark fw-bold">3. Horário de Abertura e Encerramento</h4>
      <p className="text-muted small mb-4">
        Defina os limites diários para o funcionamento da instituição escolar.
      </p>

      <CRow className="g-3">
        <CCol md={6}>
          <CFormLabel htmlFor="opening_time">Hora de Abertura da Escola *</CFormLabel>
          <CFormInput
            type="time"
            id="opening_time"
            name="opening_time"
            value={values.opening_time || '08:30'}
            invalid={Boolean(fieldErrors.opening_time)}
            onChange={(e) => onChange('opening_time', e.target.value)}
          />
          {fieldErrors.opening_time && (
            <CFormFeedback invalid>{fieldErrors.opening_time}</CFormFeedback>
          )}
        </CCol>

        <CCol md={6}>
          <CFormLabel htmlFor="closing_time">Hora de Encerramento da Escola *</CFormLabel>
          <CFormInput
            type="time"
            id="closing_time"
            name="closing_time"
            value={values.closing_time || '17:30'}
            invalid={Boolean(fieldErrors.closing_time)}
            onChange={(e) => onChange('closing_time', e.target.value)}
          />
          {fieldErrors.closing_time && (
            <CFormFeedback invalid>{fieldErrors.closing_time}</CFormFeedback>
          )}
        </CCol>
      </CRow>
    </div>
  )
}
