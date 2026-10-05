import { CFormLabel, CFormInput, CFormFeedback, CRow, CCol, CInputGroup, CInputGroupText } from '@coreui/react'
import PortugueseDateInput from '../../../components/PortugueseDateInput'

export function PeriodStep({ values, fieldErrors, onChange }) {
  return (
    <div className="foundation-step-period">
      <h4 tabIndex="-1" className="h5 mb-3 text-dark fw-bold">1. Período do Ano Letivo</h4>
      <p className="text-muted small mb-4">
        Defina o início das aulas, a data preferencial de fim e o limite final do ano letivo.
      </p>

      <CRow className="g-3">
        <CCol md={4}>
          <CFormLabel htmlFor="school_start_date">Data de Início do Ano Letivo *</CFormLabel>
          <PortugueseDateInput
            id="school_start_date"
            name="school_start_date"
            value={values.school_start_date || ''}
            invalid={Boolean(fieldErrors.school_start_date)}
            onChange={(value) => onChange('school_start_date', value)}
          />
          {fieldErrors.school_start_date && (
            <CFormFeedback invalid>{fieldErrors.school_start_date}</CFormFeedback>
          )}
        </CCol>

        <CCol md={4}>
          <CFormLabel htmlFor="preferred_end_date">Data preferencial de fim</CFormLabel>
          <PortugueseDateInput
            id="preferred_end_date"
            name="preferred_end_date"
            value={values.preferred_end_date || ''}
            min={values.school_start_date || undefined}
            max={values.school_hard_end_date || undefined}
            invalid={Boolean(fieldErrors.preferred_end_date)}
            aria-describedby="preferred_end_date-help preferred_end_date-feedback"
            onChange={(value) => onChange('preferred_end_date', value)}
          />
          <small id="preferred_end_date-help" className="text-muted d-block mt-1">
            Data até à qual o Cronos deve concluir as aulas na geração inicial do horário.
          </small>
          {fieldErrors.preferred_end_date && (
            <CFormFeedback id="preferred_end_date-feedback" className="d-block" invalid>{fieldErrors.preferred_end_date}</CFormFeedback>
          )}
        </CCol>

        <CCol md={4}>
          <CFormLabel htmlFor="school_hard_end_date">Data de Fim do Ano Letivo *</CFormLabel>
          <PortugueseDateInput
            id="school_hard_end_date"
            name="school_hard_end_date"
            value={values.school_hard_end_date || ''}
            invalid={Boolean(fieldErrors.school_hard_end_date)}
            onChange={(value) => onChange('school_hard_end_date', value)}
          />
          {fieldErrors.school_hard_end_date && (
            <CFormFeedback invalid>{fieldErrors.school_hard_end_date}</CFormFeedback>
          )}
        </CCol>

        <CCol md={12} className="mt-4">
          <CFormLabel htmlFor="repair_stability_window_days">Dias em que o horário não muda</CFormLabel>
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
            Dias a proteger: com 0, as aulas de hoje ainda podem mudar; com 1, hoje fica intacto e o dia letivo seguinte já pode ser
            reorganizado. Uma janela menor dá mais liberdade ao Cronos para construir um ano letivo mais consistente.
          </small>
          {fieldErrors.repair_stability_window_days && (
            <CFormFeedback id="repair_stability_window_days-feedback" className="d-block" invalid>{fieldErrors.repair_stability_window_days}</CFormFeedback>
          )}
        </CCol>
      </CRow>
    </div>
  )
}
