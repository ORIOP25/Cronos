import { useNavigate } from 'react-router-dom'
import { CButton } from '@coreui/react'
import { formatDate } from '../../utils/formatUtils'

const decimal = new Intl.NumberFormat('pt-PT', { maximumFractionDigits: 1 })
const ratio = (part, whole) => (whole > 0 ? decimal.format(part / whole) : '—')

export default function SchoolOverviewCard({ resources, health, isLoading }) {
  const navigate = useNavigate()
  if (isLoading) return <div className="zen-card"><div className="zen-card-body"><div className="dashboard-metric-skeleton" /></div></div>
  const counts = [
    ['teachers', 'Professores', resources?.teachers_count ?? 0],
    ['classes', 'Turmas', resources?.classes_count ?? 0],
    ['courses', 'Cursos', resources?.courses_count ?? 0],
    ['subjects', 'Disciplinas', resources?.subjects_count ?? 0],
    ['rooms', 'Salas', resources?.rooms_count ?? 0],
  ]
  const classes = resources?.classes_count ?? 0
  const ratios = [
    [ratio(resources?.teachers_count ?? 0, classes), 'professores por turma'],
    [ratio(resources?.rooms_count ?? 0, classes), 'salas por turma'],
    ...(health ? [
      [decimal.format(health.week_slots_avg), 'blocos por turma esta semana'],
      [decimal.format(health.teacher_week_slots_avg), 'blocos por professor esta semana'],
    ] : []),
  ]
  const roomsByType = Object.entries(resources?.rooms_by_type ?? {})

  return (
    <section id="schedule-health" data-testid="schedule-health" className="zen-card" aria-labelledby="school-overview-heading">
      <div className="zen-card-header"><h3 id="school-overview-heading" className="mb-0 dashboard-card-title">A escola e o horário</h3></div>
      <div className="zen-card-body school-overview">
        <dl className="school-overview__counts" data-testid="resource-counts">
          {counts.map(([key, label, value]) => <div key={key}><dt>{label}</dt><dd data-testid={`resource-${key}`}>{value}</dd></div>)}
        </dl>
        <ul className="school-overview__ratios">
          {ratios.map(([value, label]) => <li key={label}><strong>{value}</strong> {label}</li>)}
        </ul>
        {health ? (
          <p className="school-overview__schedule">
            Horário aprovado de {formatDate(health.period_start)} a {formatDate(health.period_end)}: {health.blocks_count} blocos,
            {' '}{decimal.format(health.annual_class_average)} por turma e {decimal.format(health.annual_teacher_average)} por professor no ano.
            {health.classes_empty_week > 0 && <strong className="school-overview__warning"> {health.classes_empty_week} {health.classes_empty_week === 1 ? 'turma sem aulas' : 'turmas sem aulas'} esta semana.</strong>}
            {health.classes_archived > 0 && ` Inclui ${health.classes_archived} ${health.classes_archived === 1 ? 'turma arquivada' : 'turmas arquivadas'}.`}
          </p>
        ) : (
          <div className="school-overview__schedule" data-testid="schedule-health-empty">
            <p className="mb-2 text-muted">Nenhum horário gerado.</p>
            <CButton color="primary" variant="outline" size="sm" onClick={() => navigate('/schedules?action=new')}>Criar horário</CButton>
          </div>
        )}
        {roomsByType.length > 0 && <p className="school-overview__rooms">Salas por tipo: {roomsByType.map(([type, count]) => `${type}: ${count}`).join(' · ')}</p>}
      </div>
    </section>
  )
}
