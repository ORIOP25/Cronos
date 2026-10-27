import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { formatGradeLevel } from '../../utils/presentation'

const RowSkeleton = () => <div className="dashboard-row-skeleton" />

export default function ClassProgressOverview({ progress, isLoading }) {
  const navigate = useNavigate()
  const [courseId, setCourseId] = useState('all')
  const [band, setBand] = useState('all')
  const [expanded, setExpanded] = useState(false)
  const courses = useMemo(() => [...new Map((progress ?? []).map((item) => [item.course_id, item.course_name || 'Curso sem nome'])).entries()], [progress])
  const filteredProgress = useMemo(() => (progress ?? []).filter((item) => {
    const percentage = Number(item.overall_percentage ?? 0)
    const courseMatches = courseId === 'all' || String(item.course_id) === courseId
    const bandMatches = band === 'all' || (band === 'low' && percentage < 50) || (band === 'medium' && percentage >= 50 && percentage < 80) || (band === 'high' && percentage >= 80)
    return courseMatches && bandMatches
  }).sort((left, right) => Number(left.overall_percentage ?? 0) - Number(right.overall_percentage ?? 0)), [progress, courseId, band])
  const average = progress?.length ? Math.round(progress.reduce((sum, item) => sum + item.overall_percentage, 0) / progress.length) : 0

  return (
    <div data-testid="class-progress" className="zen-card">
      <div className="zen-card-header"><h3 className="mb-0 dashboard-card-title">Progresso curricular</h3>{!isLoading && progress?.length > 0 && <span className="small text-muted">Média: {average}%</span>}</div>
      <div className="zen-card-body">
        {isLoading ? <>{Array.from({ length: 4 }, (_, index) => <RowSkeleton key={index} />)}</> : !progress?.length ? <p className="text-center text-muted py-4 mb-0" data-testid="class-progress-empty">Sem dados de progresso. Comece por registar horas nas turmas.</p> : <>
          <div className="dashboard-progress-filters">
            <label>Curso<select value={courseId} onChange={(event) => setCourseId(event.target.value)}><option value="all">Todos</option>{courses.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
            <label>Faixa de progresso<select value={band} onChange={(event) => setBand(event.target.value)}><option value="all">Todas</option><option value="low">0% a 49%</option><option value="medium">50% a 79%</option><option value="high">80% a 100%</option></select></label>
          </div>
          <div id="dashboard-class-list" className={expanded ? 'dashboard-class-list is-expanded' : 'dashboard-class-list'}>
          {!filteredProgress.length ? <p className="text-center text-muted py-4 mb-0">Não há turmas nesta seleção.</p> : (expanded ? filteredProgress : filteredProgress.slice(0, 5)).map((item) => <button key={item.class_id} type="button" data-testid="class-progress-row" className="dashboard-progress-row" onClick={() => navigate(`/courses/${item.course_id}/classes/${item.class_id}`)}>
            <div className="text-start flex-grow-1 text-truncate"><strong className="d-block text-truncate">{item.class_name}</strong><small className="text-muted">{item.course_name || '—'} · {formatGradeLevel(item.grade_level)}</small></div>
            <div className="dashboard-progress-track" aria-hidden="true"><span style={{ width: `${Math.min(item.overall_percentage, 100)}%` }} /></div>
            <strong aria-label={`${item.overall_percentage}% concluído`}>{item.overall_percentage}%</strong>
          </button>)}
          </div>
          {filteredProgress.length > 5 && <button className="btn btn-link px-0 mt-2" type="button" aria-expanded={expanded} aria-controls="dashboard-class-list" onClick={() => setExpanded(!expanded)}>{expanded ? 'Mostrar menos turmas' : `Ver todas as turmas (${filteredProgress.length})`}</button>}
        </>}
      </div>
    </div>
  )
}
