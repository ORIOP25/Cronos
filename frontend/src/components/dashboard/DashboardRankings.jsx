import { Link } from 'react-router-dom'
import { classDebtRanking, classesBehind } from '../../features/dashboard/insights'
import { formatDurationMinutes } from '../../utils/formatUtils'

const SIZE = 5

function Ranking({ title, testId, rows, empty }) {
  return (
    <div className="zen-card dashboard-ranking" data-testid={testId}>
      <div className="zen-card-header"><h3 className="mb-0 dashboard-card-title">{title}</h3></div>
      <div className="zen-card-body">
        {rows.length ? (
          <ol className="dashboard-ranking__list">
            {rows.slice(0, SIZE).map((row) => (
              <li key={row.key}>
                <Link to={row.to}><span>{row.name}</span><strong>{row.value}</strong></Link>
                {row.detail && <small>{row.detail}</small>}
              </li>
            ))}
          </ol>
        ) : <p className="text-muted small mb-0">{empty}</p>}
      </div>
    </div>
  )
}

export default function DashboardRankings({ insights, progress }) {
  const behind = classesBehind(progress ?? [], insights.planned_minutes_to_date ?? {})
  const classPath = (item) => `/courses/${item.course_id}/classes/${item.class_id}`
  const courseOf = new Map((progress ?? []).map((item) => [item.class_id, item]))
  return (
    <section className="dashboard-rankings" aria-label="Rankings">
      <Ranking
        title="Turmas mais atrasadas" testId="ranking-classes-behind" empty="Nenhuma turma abaixo do previsto."
        rows={behind.map((item) => ({
          key: item.class_id, name: item.class_name, to: classPath(item), value: `−${item.behind} p.p.`,
          detail: `${item.overall_percentage}% dado, ${item.expected}% previsto até hoje`,
        }))}
      />
      <Ranking
        title="Turmas com mais dívida" testId="ranking-classes-debt" empty="Nenhuma turma com horas em dívida."
        rows={classDebtRanking(insights.debt_weeks ?? [], progress ?? []).map((item) => ({
          key: item.class_id, name: item.class_name, value: formatDurationMinutes(item.minutes),
          to: `/absences?tab=debts&class_id=${item.class_id}`, detail: courseOf.get(item.class_id)?.course_name,
        }))}
      />
      <Ranking
        title="Professores com mais faltas" testId="ranking-teacher-absences" empty="Nenhuma falta registada este ano."
        rows={(insights.teacher_absence_minutes ?? []).map((row) => ({
          key: row.teacher_id, name: row.teacher_name, value: formatDurationMinutes(row.value),
          to: `/schedules?teacherId=${row.teacher_id}`, detail: 'Tempo de aulas em falta no ano letivo',
        }))}
      />
      <Ranking
        title="Professores com mais sumários em falta" testId="ranking-teacher-logs" empty="Todos os sumários estão registados."
        rows={(insights.teacher_missing_logs ?? []).map((row) => ({
          key: row.teacher_id, name: row.teacher_name, value: row.value,
          to: `/schedules?teacherId=${row.teacher_id}`, detail: row.value === 1 ? 'aula terminada sem sumário' : 'aulas terminadas sem sumário',
        }))}
      />
    </section>
  )
}
