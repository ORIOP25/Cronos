import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import LineChart from './LineChart'
import { debtSeries } from '../../features/dashboard/insights'
import { formatDurationHours, formatDurationMinutes } from '../../utils/formatUtils'

const COMPARE_WEEKS = 4

function Trend({ series }) {
  const latest = series.at(-1)?.minutes ?? 0
  const earlier = series.at(-1 - COMPARE_WEEKS)?.minutes
  const peak = series.reduce((best, point) => (point.minutes > best.minutes ? point : best), series[0] ?? { minutes: 0 })
  const change = earlier === undefined ? null : latest - earlier
  return (
    <div className="debt-trend__summary">
      <div><span className="dashboard-debt-value" data-alert={latest > 0} data-testid="debt-trend-latest">{formatDurationMinutes(latest)}</span><small>em dívida no fim desta semana</small></div>
      {change !== null && (
        <small className="pulse-card__note" data-trend={change > 0 ? 'bad' : change < 0 ? 'good' : undefined}>
          {change === 0 ? `Igual a há ${COMPARE_WEEKS} semanas` : `${change > 0 ? '▲ mais' : '▼ menos'} ${formatDurationMinutes(Math.abs(change))} do que há ${COMPARE_WEEKS} semanas`}
        </small>
      )}
      {peak.minutes > 0 && <small className="pulse-card__note">Pico do ano: {formatDurationMinutes(peak.minutes)}</small>}
    </div>
  )
}

export default function DebtSummaryCard({ debts, debtWeeks, progress, isLoading }) {
  const navigate = useNavigate()
  const [courseId, setCourseId] = useState('all')
  const [classId, setClassId] = useState('all')
  const courses = useMemo(() => [...new Map((progress ?? []).map((item) => [String(item.course_id), item.course_name || 'Curso sem nome'])).entries()], [progress])
  const classes = useMemo(() => (progress ?? []).filter((item) => courseId === 'all' || String(item.course_id) === courseId), [progress, courseId])
  const selected = useMemo(() => {
    if (classId !== 'all') return new Set([Number(classId)])
    if (courseId !== 'all') return new Set(classes.map((item) => item.class_id))
    return null
  }, [classId, courseId, classes])
  const series = useMemo(() => debtSeries(debtWeeks ?? [], selected), [debtWeeks, selected])
  const scope = classId !== 'all' ? `&class_id=${classId}` : ''

  return (
    <div data-testid="debt-summary" className="zen-card dashboard-debt-card">
      <div className="zen-card-header"><h3 className="mb-0 dashboard-card-title">Horas em dívida ao longo do ano</h3></div>
      <div className="zen-card-body">
        {isLoading ? <div className="dashboard-metric-skeleton" /> : <>
          <div className="dashboard-progress-filters">
            <label>Curso<select value={courseId} onChange={(event) => { setCourseId(event.target.value); setClassId('all') }}><option value="all">Toda a escola</option>{courses.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
            <label>Turma<select value={classId} onChange={(event) => setClassId(event.target.value)}><option value="all">Todas</option>{classes.map((item) => <option key={item.class_id} value={item.class_id}>{item.class_name}</option>)}</select></label>
          </div>
          {series.length > 0 ? <>
            <Trend series={series} />
            <LineChart points={series.map((point) => ({ week_start: point.week_start, value: point.minutes }))} formatValue={formatDurationMinutes} label="Horas em dívida no fim de cada semana do ano letivo" />
          </> : <p className="text-muted small mb-2">Ainda não há semanas do ano letivo para mostrar.</p>}
          <div className="debt-trend__footer">
            <small className="text-muted">
              Hoje: {formatDurationHours(debts?.total_hours_owed)} em {debts?.total_gaps ?? 0} {debts?.total_gaps === 1 ? 'furo' : 'furos'} de {debts?.affected_classes_count ?? 0} {debts?.affected_classes_count === 1 ? 'turma' : 'turmas'}
              {(debts?.total_hours_owed_overdue ?? 0) > 0 && <> · {formatDurationHours(debts.total_hours_owed_overdue)} vencidas</>}
            </small>
            <button type="button" className="btn btn-link btn-sm" onClick={() => navigate(`/absences?tab=debts${scope}`)}>Ver detalhes →</button>
          </div>
        </>}
      </div>
    </div>
  )
}
