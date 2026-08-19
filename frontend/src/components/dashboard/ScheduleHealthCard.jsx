import { useNavigate } from 'react-router-dom'
import { CButton } from '@coreui/react'

const MetricSkeleton = () => <div className="col-6 col-md-4 mb-3"><div className="dashboard-metric-skeleton mx-auto" /></div>

export default function ScheduleHealthCard({ health, isLoading }) {
  const navigate = useNavigate()
  const metrics = health ? [
    ['Turmas sem aula', health.classes_empty_week, health.classes_empty_week > 0],
    ['Média de blocos/turma', health.week_slots_avg, false],
    ['Conflitos de professor', health.duplicate_teacher_slots, health.duplicate_teacher_slots > 0],
    ['Média de blocos/professor', health.teacher_week_slots_avg, false],
    ['Variação semanal', health.weekly_fairness_spread, false],
    ['Conflitos turma', health.duplicate_class_slots, health.duplicate_class_slots > 0],
  ] : []

  return (
    <div data-testid="schedule-health" className="zen-card">
      <div className="zen-card-header"><h3 className="mb-0 dashboard-card-title">Saúde do Horário</h3></div>
      <div className="zen-card-body">
        {isLoading ? (
          <div className="row">{Array.from({ length: 6 }, (_, index) => <MetricSkeleton key={index} />)}</div>
        ) : !health ? (
          <div className="text-center py-4" data-testid="schedule-health-empty">
            <p className="mb-3 text-muted">Nenhum horário gerado.</p>
            <CButton color="primary" variant="outline" size="sm" onClick={() => navigate('/schedules?action=new')}>Criar horário</CButton>
          </div>
        ) : (
          <>
            <div className="row">
              {metrics.map(([label, value, alert]) => (
                <div key={label} className="col-6 col-md-4 mb-3 text-center">
                  <span className={`text-display d-block dashboard-health-value${alert ? ' text-danger' : ''}`}>{typeof value === 'number' ? value : '—'}</span>
                  <small className="text-uppercase text-muted">{label}</small>
                </div>
              ))}
            </div>
            <div className="small text-muted text-center">{health.blocks_count} blocos no total{health.generation_id ? ` · Geração #${health.generation_id.slice(0, 12)}...` : ''}</div>
          </>
        )}
      </div>
    </div>
  )
}
