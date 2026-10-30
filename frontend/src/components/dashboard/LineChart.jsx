const WIDTH = 600
const PAD = { top: 12, right: 12, bottom: 24, left: 44 }

const monthFormat = new Intl.DateTimeFormat('pt-PT', { month: 'short' })
const dayFormat = new Intl.DateTimeFormat('pt-PT', { day: 'numeric', month: 'short' })
const asDate = (isoDate) => new Date(`${isoDate}T12:00:00`)

/**
 * Weekly line chart in plain SVG. `compact` draws a sparkline without axes.
 * Points: [{ week_start: 'YYYY-MM-DD', value: number }].
 */
export default function LineChart({ points, formatValue = String, label, height = 160, compact = false }) {
  if (!points.length) return null
  const pad = compact ? { top: 4, right: 4, bottom: 4, left: 4 } : PAD
  const max = Math.max(...points.map((point) => point.value), 1)
  const x = (index) => pad.left + (points.length === 1 ? 0 : (index / (points.length - 1)) * (WIDTH - pad.left - pad.right))
  const y = (value) => height - pad.bottom - (value / max) * (height - pad.top - pad.bottom)
  const line = points.map((point, index) => `${x(index)},${y(point.value)}`).join(' ')
  const last = points.at(-1)
  const months = points.filter((point, index) => index === 0 || asDate(point.week_start).getMonth() !== asDate(points[index - 1].week_start).getMonth())

  return (
    <svg className={compact ? 'line-chart line-chart--compact' : 'line-chart'} viewBox={`0 0 ${WIDTH} ${height}`} role="img" aria-label={label}>
      {!compact && <>
        <line className="line-chart__grid" x1={pad.left} x2={WIDTH - pad.right} y1={y(0)} y2={y(0)} />
        <line className="line-chart__grid is-dashed" x1={pad.left} x2={WIDTH - pad.right} y1={y(max)} y2={y(max)} />
        <text className="line-chart__axis" x={pad.left - 6} y={y(0) + 4} textAnchor="end">0</text>
        <text className="line-chart__axis" x={pad.left - 6} y={y(max) + 4} textAnchor="end">{formatValue(max)}</text>
        {months.map((point) => <text key={point.week_start} className="line-chart__axis" x={x(points.indexOf(point))} y={height - 6}>{monthFormat.format(asDate(point.week_start))}</text>)}
      </>}
      <polyline className="line-chart__line" points={line} />
      {!compact && points.map((point, index) => (
        <circle key={point.week_start} className="line-chart__point" cx={x(index)} cy={y(point.value)} r="6">
          <title>{`Semana de ${dayFormat.format(asDate(point.week_start))}: ${formatValue(point.value)}`}</title>
        </circle>
      ))}
      <circle className="line-chart__last" cx={x(points.length - 1)} cy={y(last.value)} r={compact ? 4 : 5} />
    </svg>
  )
}
