import { Link } from 'react-router-dom'
import LineChart from './LineChart'
import { pulseSummary } from '../../features/dashboard/insights'
import { formatDurationMinutes } from '../../utils/formatUtils'

const TREND_WEEKS = 12

function addDays(isoDate, days) {
  const date = new Date(`${isoDate}T12:00:00`)
  date.setDate(date.getDate() + days)
  return date.toISOString().slice(0, 10)
}

function Delta({ current, previous }) {
  if (current === null || previous === null) return <small className="pulse-card__note">Sem comparação com a semana passada</small>
  const change = current - previous
  if (change === 0) return <small className="pulse-card__note">Igual à semana passada ({previous}%)</small>
  return <small className="pulse-card__note" data-trend={change > 0 ? 'good' : 'bad'}>{change > 0 ? '▲' : '▼'} {Math.abs(change)} p.p. face à semana passada</small>
}

function PulseCard({ testId, label, value, note, trend, trendLabel, formatValue, to }) {
  return (
    <Link to={to} className="pulse-card" data-testid={testId}>
      <span className="pulse-card__label">{label}</span>
      <strong className="pulse-card__value">{value}</strong>
      {note}
      <LineChart compact height={40} points={trend} formatValue={formatValue} label={trendLabel} />
    </Link>
  )
}

export default function WeeklyPulse({ weeks }) {
  const summary = pulseSummary(weeks)
  const { current, previous } = summary
  if (!current) return null
  const recent = weeks.slice(-TREND_WEEKS)
  const series = (value) => recent.map((week) => ({ week_start: week.week_start, value: value(week) }))
  const weekEnd = addDays(current.week_start, 6)
  const rate = (part, whole) => (whole > 0 ? Math.round((part / whole) * 100) : 0)
  const percent = (value) => `${value}%`

  return (
    <section className="weekly-pulse" aria-labelledby="weekly-pulse-heading">
      <h2 id="weekly-pulse-heading" className="weekly-pulse__heading">Esta semana <small>até agora, com as últimas {recent.length} semanas</small></h2>
      <div className="weekly-pulse__cards">
        <PulseCard
          testId="pulse-given" label="Aulas dadas" to={`/absences?date_from=${current.week_start}&date_to=${weekEnd}`}
          value={summary.givenRate === null ? '—' : `${summary.givenRate}%`}
          note={<Delta current={summary.givenRate} previous={summary.previousGivenRate} />}
          trend={series((week) => rate(week.lessons_given, week.lessons_due))} formatValue={percent}
          trendLabel="Percentagem de aulas dadas por semana"
        />
        <PulseCard
          testId="pulse-absences" label="Faltas de professores" to={`/absences?date_from=${current.week_start}&date_to=${weekEnd}`}
          value={formatDurationMinutes(current.absence_minutes)}
          note={<small className="pulse-card__note">Semana passada: {formatDurationMinutes(previous?.absence_minutes ?? 0)}</small>}
          trend={series((week) => week.absence_minutes)} formatValue={formatDurationMinutes}
          trendLabel="Tempo de faltas de professores por semana"
        />
        <PulseCard
          testId="pulse-coverage" label="Faltas cobertas por substituição" to={`/absences?status=SUBSTITUTED&date_from=${current.week_start}&date_to=${weekEnd}`}
          value={summary.coverageRate === null ? '—' : `${summary.coverageRate}%`}
          note={<small className="pulse-card__note">Média do ano: {summary.yearCoverageRate === null ? '—' : `${summary.yearCoverageRate}%`}</small>}
          trend={series((week) => rate(week.substituted_minutes, week.absence_minutes))} formatValue={percent}
          trendLabel="Percentagem de faltas cobertas por semana"
        />
        <PulseCard
          testId="pulse-missing-logs" label="Sumários em falta" to="/timesheets"
          value={current.missing_logs}
          note={<small className="pulse-card__note">{summary.yearMissingLogs} no ano letivo</small>}
          trend={series((week) => week.missing_logs)} formatValue={String}
          trendLabel="Sumários em falta por semana"
        />
      </div>
    </section>
  )
}
