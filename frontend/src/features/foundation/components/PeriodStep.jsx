import { CFormLabel, CFormInput, CFormFeedback, CRow, CCol, CInputGroup, CInputGroupText } from '@coreui/react'

export function PeriodStep({ values, fieldErrors, onChange }) {
  return (
    <div className="foundation-step-period">
      <h4 tabIndex="-1" className="h5 mb-3 text-dark fw-bold">1. Período do Ano Letivo</h4>
      <p className="text-muted small mb-4">
        Defina o horizonte temporal da sua escola. O Cronos calculará se a totalidade das horas curriculares pode ser ministrada até à data-limite rígida.
      </p>

      <CRow className="g-3">
        <CCol md={6}>
          <CFormLabel htmlFor="school_start_date">Data de Início do Ano Letivo *</CFormLabel>
          <CFormInput
            type="date"
            id="school_start_date"
            name="school_start_date"
            value={values.school_start_date || ''}
            invalid={Boolean(fieldErrors.school_start_date)}
            onChange={(e) => onChange('school_start_date', e.target.value)}
          />
          {fieldErrors.school_start_date && (
            <CFormFeedback invalid>{fieldErrors.school_start_date}</CFormFeedback>
          )}
        </CCol>

        <CCol md={6}>
          <CFormLabel htmlFor="school_hard_end_date">Data-Limite Rígida *</CFormLabel>
          <CFormInput
            type="date"
            id="school_hard_end_date"
            name="school_hard_end_date"
            value={values.school_hard_end_date || ''}
            invalid={Boolean(fieldErrors.school_hard_end_date)}
            onChange={(e) => onChange('school_hard_end_date', e.target.value)}
          />
          {fieldErrors.school_hard_end_date && (
            <CFormFeedback invalid>{fieldErrors.school_hard_end_date}</CFormFeedback>
          )}
        </CCol>

        <CCol md={12} className="mt-4">
          <CFormLabel htmlFor="repair_stability_window_days">Janela de Estabilidade de Reparação</CFormLabel>
          <CInputGroup>
            <CFormInput
              type="number"
              id="repair_stability_window_days"
              name="repair_stability_window_days"
              min={0}
              max={60}
              value={values.repair_stability_window_days ?? 14}
              invalid={Boolean(fieldErrors.repair_stability_window_days)}
              aria-describedby="repair_stability_window_days-unit repair_stability_window_days-feedback"
              onChange={(e) => onChange('repair_stability_window_days', e.target.value)}
              onBlur={() => {
                if (values.repair_stability_window_days === '') onChange('repair_stability_window_days', 0)
              }}
            />
            <CInputGroupText id="repair_stability_window_days-unit">Dias</CInputGroupText>
          </CInputGroup>
          <small className="text-muted d-block mt-1">
            Número de dias no futuro imediato cujos horários ficam protegidos durante reparações adaptativas (omissão: 14 dias).
          </small>
          {fieldErrors.repair_stability_window_days && (
            <CFormFeedback id="repair_stability_window_days-feedback" className="d-block" invalid>{fieldErrors.repair_stability_window_days}</CFormFeedback>
          )}
        </CCol>
      </CRow>
    </div>
  )
}
