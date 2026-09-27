import { CCard, CCardBody, CRow, CCol, CFormCheck } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilCalendar, cilClock } from '@coreui/icons'
import { formatTimeOfDay } from '../../../utils/timeOfDay'
import { normalizeBreakOverrides } from '../foundationModel'

const DAY_NAMES = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']

export function SummaryStep({ values, organizationName, confirmed, onConfirmedChange }) {
  const days = (values.days_of_week || []).map((d) => DAY_NAMES[d] || `Dia ${d}`).join(', ')
  const overrides = normalizeBreakOverrides(values.break_overrides)
  const adjustments = overrides.length
    ? overrides.map((override) => `após aula ${override.after_slot} (${override.duration_minutes} min)`).join(', ')
    : 'nenhum'
  const flows = (values.internship_flows || []).filter((flow) => flow.name && flow.start_date && flow.end_date)

  return (
    <div className="foundation-step-summary">
      <h4 tabIndex="-1" className="h5 mb-3 text-dark fw-bold">10. Confirmação e Ativação da Fundação</h4>
      <p className="text-muted small mb-4">
        Reveja os parâmetros base para <strong>{organizationName}</strong>. Ao clicar em &quot;Ativar Escola&quot;, a fundação será concluída de forma definitiva e irreversível, criando a grelha horária canónica e desbloqueando a fase de preparação.
      </p>

      <CRow className="g-3 mb-4">
        <CCol md={6}>
          <CCard className="h-100 border-0 shadow-sm bg-light">
            <CCardBody>
              <h6 className="fw-bold text-primary mb-3"><CIcon icon={cilCalendar} className="me-2" aria-hidden="true" />Período Escolar</h6>
              <div className="small mb-2">
                <span className="text-muted d-block">Data de Início:</span>
                <strong>{values.school_start_date || '—'}</strong>
              </div>
              <div className="small mb-2">
                <span className="text-muted d-block">Data-Limite Rígida:</span>
                <strong>{values.school_hard_end_date || '—'}</strong>
              </div>
              <div className="small">
                <span className="text-muted d-block">Janela de Estabilidade:</span>
                <strong>{values.repair_stability_window_days ?? 14} dias</strong>
              </div>
              <div className="small mt-2">
                <span className="text-muted d-block">Feriados automáticos:</span>
                <strong>{values.automatic_holidays_enabled ? 'Ativados' : 'Desativados'}</strong>
              </div>
              <div className="small mt-2">
                <span className="text-muted d-block">Fluxos de estágio:</span>
                <strong>
                  {flows.length
                    ? flows.map((flow) => `${flow.name} (${flow.start_date} a ${flow.end_date})`).join('; ')
                    : 'Nenhum'}
                </strong>
              </div>
            </CCardBody>
          </CCard>
        </CCol>

        <CCol md={6}>
          <CCard className="h-100 border-0 shadow-sm bg-light">
            <CCardBody>
              <h6 className="fw-bold text-primary mb-3"><CIcon icon={cilClock} className="me-2" aria-hidden="true" />Grelha Horária</h6>
              <div className="small mb-2">
                <span className="text-muted d-block">Dias de Aulas:</span>
                <strong>{days || 'Nenhum'}</strong>
              </div>
              <div className="small mb-2">
                <span className="text-muted d-block">Horário de Funcionamento:</span>
                <strong>{formatTimeOfDay(values.opening_time)} às {formatTimeOfDay(values.closing_time)}</strong>
              </div>
              <div className="small mb-2">
                <span className="text-muted d-block">Bloco / Intervalo:</span>
                <strong>{values.slot_duration_minutes} min / {values.break_duration_minutes} min</strong>
              </div>
              <div className="small mb-2">
                <span className="text-muted d-block">Pausas entre Aulas:</span>
                <strong>Pausa habitual: {values.break_duration_minutes} min · Ajustes: {adjustments}</strong>
              </div>
              <div className="small">
                <span className="text-muted d-block">Janela de Almoço:</span>
                <strong>{formatTimeOfDay(values.lunch_window_start)} - {formatTimeOfDay(values.lunch_window_end)} (mín. {values.lunch_min_duration_minutes} min)</strong>
              </div>
            </CCardBody>
          </CCard>
        </CCol>
      </CRow>

      <CFormCheck
        id="foundation-confirmation"
        className="mt-3"
        checked={confirmed}
        onChange={(event) => onConfirmedChange(event.target.checked)}
        label="Confirmo que revi os parâmetros e autorizo a ativação definitiva da fundação."
      />
    </div>
  )
}
