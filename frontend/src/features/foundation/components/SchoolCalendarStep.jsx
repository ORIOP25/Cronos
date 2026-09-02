import { CCard, CCardBody, CFormCheck } from '@coreui/react'

export function SchoolCalendarStep({ values, onChange }) {
  return (
    <div className="foundation-step-calendar">
      <h4 tabIndex="-1" className="h5 mb-3 text-dark fw-bold">8. Feriados e Pausas Letivas</h4>
      <p className="text-muted small mb-4">
        Configure o calendário escolar para o período {values.school_start_date || 'Início'} a {values.school_hard_end_date || 'Fim'}.
      </p>

      <CCard className="border-0 shadow-sm bg-light mb-4">
        <CCardBody>
          <h6 className="fw-bold text-secondary mb-3">Feriados nacionais</h6>
          <CFormCheck
            id="automatic_holidays_enabled"
            label="Feriados automáticos"
            checked={Boolean(values.automatic_holidays_enabled)}
            onChange={(event) => onChange('automatic_holidays_enabled', event.target.checked)}
          />
          <p className="text-muted small mb-0 mt-2">
            Ativar importa os feriados nacionais e acompanha alterações futuras às datas do período letivo.
          </p>
        </CCardBody>
      </CCard>
    </div>
  )
}
