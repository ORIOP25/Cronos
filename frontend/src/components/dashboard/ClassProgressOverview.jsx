import { useNavigate } from 'react-router-dom'
import { formatGradeLevel } from '../../utils/presentation'

const RowSkeleton = () => <div className="dashboard-row-skeleton" />

export default function ClassProgressOverview({ progress, isLoading }) {
  const navigate = useNavigate()
  const average = progress?.length
    ? Math.round(progress.reduce((sum, item) => sum + item.overall_percentage, 0) / progress.length)
    : 0

  return (
    <div data-testid="class-progress" className="zen-card">
      <div className="zen-card-header">
        <h3 className="mb-0 dashboard-card-title">Progresso Curricular</h3>
        {!isLoading && progress?.length > 0 && <span className="small text-muted">Média: {average}%</span>}
      </div>
      <div className="zen-card-body">
        {isLoading ? (
          <>{Array.from({ length: 4 }, (_, index) => <RowSkeleton key={index} />)}</>
        ) : !progress?.length ? (
          <p className="text-center text-muted py-4 mb-0" data-testid="class-progress-empty">Sem dados de progresso. Comece por registar horas nas turmas.</p>
        ) : progress.map((item) => (
          <button key={item.class_id} type="button" data-testid="class-progress-row" className="dashboard-progress-row" onClick={() => navigate(`/courses/${item.course_id}/classes/${item.class_id}`)}>
            <div className="text-start flex-grow-1 text-truncate">
              <strong className="d-block text-truncate">{item.class_name}</strong>
              <small className="text-muted">{item.course_name || '—'} · {formatGradeLevel(item.grade_level)}</small>
            </div>
            <div className="dashboard-progress-track"><span style={{ width: `${Math.min(item.overall_percentage, 100)}%` }} /></div>
            <strong className={item.overall_percentage < 50 ? 'text-danger' : 'text-success'}>{item.overall_percentage}%</strong>
          </button>
        ))}
      </div>
    </div>
  )
}
