import { CCard, CCardBody, CBadge } from '@coreui/react'

export function SchoolCalendarStep({ values }) {
  return (
    <div className="foundation-step-calendar">
      <h4 tabIndex="-1" className="h5 mb-3 text-dark fw-bold">8. Feriados e Pausas Letivas</h4>
      <p className="text-muted small mb-4">
        Configure feriados e pausas letivas por comando explícito para o período ({values.school_start_date || 'Início'} a {values.school_hard_end_date || 'Fim'}). Esta fundação não os sincroniza nem persiste.
      </p>

      <CCard className="border-0 shadow-sm bg-light mb-4">
        <CCardBody>
          <div className="d-flex justify-content-between align-items-center mb-3">
            <h6 className="fw-bold text-secondary mb-0">Feriados e pausas configuráveis</h6>
            <CBadge color="secondary">Configuração explícita</CBadge>
          </div>
          <p className="text-muted small mb-0">
            Use a área de configuração escolar para registar as restrições que devem ser usadas na geração e nos sumários.
          </p>
        </CCardBody>
      </CCard>
    </div>
  )
}
