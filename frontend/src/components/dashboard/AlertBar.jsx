import { useNavigate } from 'react-router-dom'
import StatePanel from '../StatePanel'
import { formatDate } from '../../utils/formatUtils'

const DAY = 24 * 60 * 60 * 1000

function ageLabel(isoDate) {
  if (!isoDate) return null
  const days = Math.floor((Date.now() - new Date(`${isoDate}T00:00:00`).getTime()) / DAY)
  if (days <= 0) return 'a mais antiga é de hoje'
  return days === 1 ? 'a mais antiga tem 1 dia' : `a mais antiga tem ${days} dias`
}

function attentionItems(alerts) {
  const occurrences = Number(alerts?.pending_occurrences_total ?? 0)
  const upcoming = Number(alerts?.pending_occurrences_upcoming ?? 0)
  const timesheets = Number(alerts?.pending_timesheets ?? 0)
  const drafts = Number(alerts?.pending_drafts ?? 0)
  return [
    {
      key: 'occurrences', count: occurrences, tone: upcoming > 0 ? 'danger' : 'warning',
      label: occurrences === 1 ? 'falta por decidir' : 'faltas por decidir',
      detail: [upcoming > 0 && `${upcoming} com aula hoje ou mais tarde`, ageLabel(alerts?.oldest_pending_occurrence_date)].filter(Boolean).join(' · '),
      action: 'Decidir', route: '/absences?status=OPEN',
    },
    {
      key: 'timesheets', count: timesheets, tone: 'warning',
      label: timesheets === 1 ? 'folha de horas por aprovar' : 'folhas de horas por aprovar',
      detail: alerts?.oldest_pending_timesheet_week ? `desde a semana de ${formatDate(alerts.oldest_pending_timesheet_week)}` : '',
      action: 'Rever', route: '/timesheets?status=submitted',
    },
    {
      key: 'drafts', count: drafts, tone: 'neutral',
      label: drafts === 1 ? 'rascunho de horário' : 'rascunhos de horário',
      detail: 'Aprove ou rejeite antes de gerar outra versão.',
      action: 'Comparar', route: '/schedules?tab=drafts',
    },
  ].filter((item) => item.count > 0)
}

function healthyFacts(alerts, currentWeek) {
  const facts = []
  if (currentWeek?.lessons_due > 0) {
    const logged = currentWeek.lessons_due - currentWeek.missing_logs
    facts.push(`Sumários desta semana: ${Math.round((logged / currentWeek.lessons_due) * 100)}%`)
  }
  // Only reassuring when older absences are still open; with no tasks the heading says it.
  if (Number(alerts?.pending_occurrences_total ?? 0) > 0 && Number(alerts?.pending_occurrences_today ?? 0) === 0) facts.push('Nenhuma falta de hoje por decidir')
  const substitutions = Number(alerts?.active_substitutions_today ?? 0)
  if (substitutions > 0) facts.push(`${substitutions} ${substitutions === 1 ? 'substituição' : 'substituições'} hoje`)
  return facts
}

export default function AlertBar({ alerts, currentWeek, isLoading }) {
  const navigate = useNavigate()
  if (isLoading) return <div data-testid="alert-bar"><StatePanel state="loading" title="A verificar o que requer atenção" compact /></div>
  const items = attentionItems(alerts)
  const total = items.reduce((sum, item) => sum + item.count, 0)
  const facts = healthyFacts(alerts, currentWeek)
  return (
    <section className="attention-panel" data-testid="alert-bar" data-clear={items.length === 0} aria-labelledby="attention-heading">
      <div className="attention-panel__heading">
        {items.length ? (
          <>
            <h2 id="attention-heading">A requerer atenção</h2>
            <span>{`${total} ${total === 1 ? 'tarefa pendente' : 'tarefas pendentes'}`}</span>
          </>
        ) : <h2 id="attention-heading">Sem tarefas pendentes</h2>}
      </div>
      {items.length > 0 && (
        <div className="attention-panel__items">
          {items.map((item) => (
            <button key={item.key} type="button" className="attention-item" data-tone={item.tone} data-testid={`alert-${item.key}`} onClick={() => navigate(item.route)}>
              <strong>{item.count}</strong>
              <span><b>{item.label}</b>{item.detail && <small>{item.detail}</small>}</span>
              <span className="attention-item__action">{item.action} <span aria-hidden="true">→</span></span>
            </button>
          ))}
        </div>
      )}
      {facts.length > 0 && (
        <ul className="attention-panel__facts" aria-label="Estado operacional">
          {facts.map((fact) => <li key={fact}>{fact}</li>)}
        </ul>
      )}
    </section>
  )
}
