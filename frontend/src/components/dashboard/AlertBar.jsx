import { useNavigate } from 'react-router-dom'
import StatePanel from '../StatePanel'

const attentionItems = [
  { key: 'occurrences', label: 'ocorrências por rever', explanation: 'Há decisões operacionais pendentes.', route: '/absences?status=OPEN', field: 'pending_occurrences_total' },
  { key: 'timesheets', label: 'folhas de horas submetidas', explanation: 'Reveja os registos semanais da equipa.', route: '/timesheets?status=submitted', field: 'pending_timesheets' },
  { key: 'drafts', label: 'rascunhos de horário', explanation: 'Aprovar ou rejeitar antes de gerar outra versão.', route: '/schedules?tab=drafts', field: 'pending_drafts' },
  { key: 'substitutions', label: 'substituições ativas', explanation: 'Confirme a cobertura das aulas.', route: '/absences?status=SUBSTITUTED', field: 'active_substitutions_today' },
]

export default function AlertBar({ alerts, health, isLoading }) {
  const navigate = useNavigate()
  if (isLoading) return <div data-testid="alert-bar"><StatePanel state="loading" title="A verificar o que requer atenção" compact /></div>
  const items = [
    ...attentionItems.map((item) => ({ ...item, count: Number(alerts?.[item.field] ?? 0) })),
    { key: 'conflicts', label: 'conflitos no horário', explanation: 'Identifique os blocos em conflito na Saúde do Horário.', route: '#schedule-health', count: (health?.duplicate_teacher_slots ?? 0) + (health?.duplicate_class_slots ?? 0) },
  ].filter((item) => item.count > 0)
  const openItem = (item) => {
    if (item.key !== 'conflicts') return navigate(item.route)
    const healthCard = document.getElementById('schedule-health')
    healthCard?.focus()
    healthCard?.scrollIntoView({ block: 'start' })
  }
  return (
    <section className="attention-panel" data-testid="alert-bar" aria-labelledby="attention-heading">
      <div className="attention-panel__heading"><h2 id="attention-heading">A requerer atenção</h2><span>{items.length ? `${items.length} áreas` : 'Tudo controlado'}</span></div>
      {items.length ? <div className="attention-panel__items">{items.map((item) => <button key={item.key} type="button" className="attention-item" data-testid={`alert-${item.key}`} onClick={() => openItem(item)}><strong>{item.count}</strong><span><b>{item.label}</b><small>{item.explanation}</small></span><span aria-hidden="true">→</span></button>)}</div> : <p className="attention-panel__empty">Não há intervenções pendentes neste momento.</p>}
    </section>
  )
}
