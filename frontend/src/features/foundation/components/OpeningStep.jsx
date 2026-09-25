import { CRow, CCol } from '@coreui/react'
import { TimeField } from '../../../components/TimeField'

export function OpeningStep({ values, fieldErrors, onChange }) {
  return (
    <div className="foundation-step-opening">
      <h4 tabIndex="-1" className="h5 mb-3 text-dark fw-bold">3. Horário de Abertura e Encerramento</h4>
      <p className="text-muted small mb-4">
        Defina os limites diários para o funcionamento da instituição escolar.
      </p>

      <CRow className="g-3">
        <CCol md={6}>
          <TimeField
            id="opening_time"
            label="Hora de Abertura da Escola *"
            value={values.opening_time || '08:30'}
            error={fieldErrors.opening_time}
            onChange={(value) => onChange('opening_time', value)}
          />
        </CCol>

        <CCol md={6}>
          <TimeField
            id="closing_time"
            label="Hora de Encerramento da Escola *"
            value={values.closing_time || '17:30'}
            error={fieldErrors.closing_time}
            onChange={(value) => onChange('closing_time', value)}
          />
        </CCol>
      </CRow>
    </div>
  )
}
