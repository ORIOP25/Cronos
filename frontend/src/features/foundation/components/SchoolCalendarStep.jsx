import { CCard, CCardBody, CBadge } from '@coreui/react'

export function SchoolCalendarStep({ values }) {
  return (
    <div className="foundation-step-calendar">
      <h4 className="h5 mb-3 text-dark fw-bold">8. Feriados e Pausas Letivas</h4>
      <p className="text-muted small mb-4">
        O Cronos sincroniza automaticamente os feriados oficiais de Portugal durante o período letivo ({values.school_start_date || 'Início'} a {values.school_hard_end_date || 'Fim'}). Poderá adicionar pausas letivas específicas (ex: férias de Carnaval ou Páscoa) a qualquer momento nas configurações escolares.
      </p>

      <CCard className="border-0 shadow-sm bg-light mb-4">
        <CCardBody>
          <div className="d-flex justify-content-between align-items-center mb-3">
            <h6 className="fw-bold text-secondary mb-0">Sincronização de Calendário Nacional</h6>
            <CBadge color="success">Automático</CBadge>
          </div>
          <p className="text-muted small mb-0">
            Feriados nacionais obrigatórios e dias não letivos serão integrados como restrições rígidas (hard constraints) no gerador de horários e no livro de sumários.
          </p>
        </CCardBody>
      </CCard>
    </div>
  )
}
