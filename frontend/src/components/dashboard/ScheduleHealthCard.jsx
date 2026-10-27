import { Link, useNavigate } from 'react-router-dom'
import { CButton } from '@coreui/react'
import { formatDate, toWeekMonday } from '../../utils/formatUtils'

const MetricSkeleton = () => <div className="col-6 col-md-4 mb-3"><div className="dashboard-metric-skeleton mx-auto" /></div>

export default function ScheduleHealthCard({ health, isLoading }) {
  const navigate = useNavigate()
  const metrics = health ? [
    ['Turmas sem aula', health.classes_empty_week, health.classes_empty_week > 0],
    ['Média de blocos/turma (semana)', health.week_slots_avg, false],
    ['Conflitos de professor', health.duplicate_teacher_slots, health.duplicate_teacher_slots > 0],
    ['Média de blocos/professor (semana)', health.teacher_week_slots_avg, false],
    ['Variação semanal', health.weekly_fairness_spread, false],
    ['Conflitos turma', health.duplicate_class_slots, health.duplicate_class_slots > 0],
  ] : []
  const periodLabel = health?.period_start && health?.period_end
    ? `${formatDate(health.period_start)} – ${formatDate(health.period_end)}`
    : null

  return (
    <div id="schedule-health" data-testid="schedule-health" className="zen-card" tabIndex={-1}>
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
            <div className="row mb-1">
              <div className="col-6 mb-3 text-center">
                <span className="text-display d-block dashboard-health-value">{health.annual_class_average ?? '—'}</span>
                <small className="text-uppercase text-muted">Média anual por turma</small>
              </div>
              <div className="col-6 mb-3 text-center">
                <span className="text-display d-block dashboard-health-value">{health.annual_teacher_average ?? '—'}</span>
                <small className="text-uppercase text-muted">Média anual por professor</small>
              </div>
            </div>
            <div className="small text-muted text-center mb-3">
              {health.classes_total} turmas e {health.teachers_total} professores no horário aprovado
              {periodLabel ? ` · ${periodLabel}` : ''}
              {health.classes_archived > 0 && (
                <div>Inclui {health.classes_archived} {health.classes_archived === 1 ? 'turma arquivada' : 'turmas arquivadas'}.
                  {' '}O catálogo apresenta apenas turmas ativas. A média usa todas as turmas do horário aprovado.
                </div>
              )}
            </div>
            <div className="dashboard-health-metrics">
              {metrics.map(([label, value, alert]) => (
                <div key={label} className="dashboard-health-metric">
                  <span className={`text-display d-block dashboard-health-value${alert ? ' text-danger' : ''}`}>{typeof value === 'number' ? value : '—'}</span>
                  <small className="text-muted">{label}</small>
                </div>
              ))}
            </div>
            <div className="small text-muted text-center">{health.blocks_count} blocos no total</div>
            {health.conflicting_lessons?.length > 0 && (
              <details className="context-details dashboard-conflicts mt-3">
                <summary>Blocos em conflito ({health.conflicting_lessons.length})</summary>
                <ul className="context-list" aria-label="Blocos em conflito" tabIndex={0}>
                  {health.conflicting_lessons.map((lesson) => (
                    <li key={lesson.lesson_id} className="mb-2">
                      <strong className="d-block">{lesson.class_name} · {lesson.subject_name}</strong>
                      <span className="d-block text-muted">{lesson.teacher_name} · Bloco {lesson.lesson_id}</span>
                      <div>
                        {formatDate(lesson.school_date)} · {new Date(lesson.starts_at).toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Lisbon' })}
                        {'–'}{new Date(lesson.ends_at).toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Lisbon' })}
                        {' · '}<Link to={`/schedules?teacherId=${lesson.teacher_id}&weekStart=${toWeekMonday(lesson.school_date)}`} aria-label={`Abrir semana do bloco ${lesson.lesson_id}`}>Abrir semana</Link>
                      </div>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </>
        )}
      </div>
    </div>
  )
}
