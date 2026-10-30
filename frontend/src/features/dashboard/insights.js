// Local calendar day as YYYY-MM-DD, comparable with the API's school dates.
export const isoToday = () => new Date().toLocaleDateString('sv-SE')

const percentage = (part, whole) => (whole > 0 ? Math.round((part / whole) * 100) : null)

const sum = (items, field) => items.reduce((total, item) => total + item[field], 0)

export function pulseSummary(weeks) {
  const current = weeks.at(-1) ?? null
  const previous = weeks.at(-2) ?? null
  return {
    current,
    previous,
    givenRate: current && percentage(current.lessons_given, current.lessons_due),
    previousGivenRate: previous && percentage(previous.lessons_given, previous.lessons_due),
    coverageRate: current && percentage(current.substituted_minutes, current.absence_minutes),
    yearCoverageRate: percentage(sum(weeks, 'substituted_minutes'), sum(weeks, 'absence_minutes')),
    yearMissingLogs: sum(weeks, 'missing_logs'),
  }
}

export function debtSeries(debtWeeks, classIds) {
  return debtWeeks.map((week) => ({
    week_start: week.week_start,
    minutes: Object.entries(week.minutes_by_class)
      .filter(([classId]) => !classIds || classIds.has(Number(classId)))
      .reduce((total, [, minutes]) => total + minutes, 0),
  }))
}

export function expectedPercentage(item, plannedMinutes) {
  if (!item.total_hours) return null
  return Math.min(100, Math.round(((plannedMinutes[item.class_id] ?? 0) / (item.total_hours * 60)) * 100))
}

export function classesBehind(progress, plannedMinutes) {
  return progress
    .map((item) => {
      const expected = expectedPercentage(item, plannedMinutes)
      return { ...item, expected, behind: expected === null ? 0 : Math.round(expected - item.overall_percentage) }
    })
    .filter((item) => item.behind > 0)
    .sort((left, right) => right.behind - left.behind)
}

export function classDebtRanking(debtWeeks, progress) {
  const latest = debtWeeks.at(-1)?.minutes_by_class ?? {}
  // ponytail: archived classes have no progress row, so they stay in the school total only.
  return progress
    .filter((item) => latest[item.class_id] > 0)
    .map((item) => ({ class_id: item.class_id, class_name: item.class_name, minutes: latest[item.class_id] }))
    .sort((left, right) => right.minutes - left.minutes)
}
