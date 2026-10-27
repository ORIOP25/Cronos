import { CFormCheck } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilCalendar, cilClock } from '@coreui/icons'
import { DAY_LABELS } from '../../../constants'
import { formatTimeOfDay } from '../../../utils/timeOfDay'
import { normalizeBreakOverrides } from '../foundationModel'

export function SummaryStep({ values, organizationName, confirmed, onConfirmedChange }) {
  const days = (values.days_of_week || []).map((day) => DAY_LABELS[day] || `Dia ${day}`).join(', ')
  const overrides = normalizeBreakOverrides(values.break_overrides)
  const adjustments = overrides.length
    ? overrides.map((override) => `após aula ${override.after_slot} (${override.duration_minutes} min)`).join(', ')
    : 'nenhum'
  const flows = (values.internship_flows || []).filter((flow) => flow.name && flow.start_date && flow.end_date)
  const groups = [
    { title: 'Período Escolar', icon: cilCalendar, items: [
      ['Data de Início:', values.school_start_date || '—'],
      ['Data preferencial de fim:', values.preferred_end_date || '—'],
      ['Fim do ano letivo:', values.school_hard_end_date || '—'],
      ['Dias em que o horário não muda:', `${values.repair_stability_window_days ?? 14} dias`],
      ['Feriados automáticos:', values.automatic_holidays_enabled ? 'Ativados' : 'Desativados'],
      ['Fluxos de estágio:', flows.length ? flows.map((flow) => `${flow.name} (${flow.start_date} a ${flow.end_date})`).join('; ') : 'Nenhum'],
    ] },
    { title: 'Grelha Horária', icon: cilClock, items: [
      ['Dias de Aulas:', days || 'Nenhum'],
      ['Horário de Funcionamento:', `${formatTimeOfDay(values.opening_time)} às ${formatTimeOfDay(values.closing_time)}`],
      ['Duração da aula:', `${values.slot_duration_minutes} min`],
      ['Pausas entre Aulas:', `Pausa habitual: ${values.break_duration_minutes} min · Ajustes: ${adjustments}`],
      ['Janela de Almoço:', `${formatTimeOfDay(values.lunch_window_start)} - ${formatTimeOfDay(values.lunch_window_end)} (mín. ${values.lunch_min_duration_minutes} min)`],
    ] },
  ]

  return (
    <div className="foundation-step-summary">
      <h4 tabIndex="-1" className="h5 mb-3 text-dark fw-bold">10. Confirmação e Ativação da Fundação</h4>
      <p className="text-muted small mb-4">
        Reveja os parâmetros base para <strong>{organizationName}</strong>. Ao clicar em &quot;Ativar Escola&quot;, a fundação será concluída de forma definitiva e irreversível, criando a grelha horária canónica e desbloqueando a fase de preparação.
      </p>
      <div className="row g-4 mb-4">
        {groups.map((group) => <section key={group.title} className="col-md-6" aria-label={group.title}>
          <h5 className="h6 fw-bold mb-3"><CIcon icon={group.icon} className="me-2" aria-hidden="true" />{group.title}</h5>
          <dl className="summary-list">
            {group.items.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
          </dl>
        </section>)}
      </div>
      <CFormCheck
        id="foundation-confirmation"
        className="mt-3"
        checked={confirmed}
        onChange={(event) => onConfirmedChange(event.target.checked)}
        label="Confirmo que revi os dados e autorizo a ativação da escola."
      />
    </div>
  )
}
