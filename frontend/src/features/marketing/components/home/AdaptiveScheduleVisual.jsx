import SemanticIcon from '../shared/SemanticIcon'
import { adaptiveStates } from '../../content/home'

const scheduleRows = [
  ['is-fixed', 'is-fixed', 'is-open', 'is-open'],
  ['is-fixed', 'is-fixed', 'is-shifted', 'is-shifted'],
  ['is-fixed', 'is-open', 'is-shifted', 'is-approved'],
]

export default function AdaptiveScheduleVisual() {
  return (
    <div className="cronos-adaptive-visual">
      <div className="cronos-adaptive-visual__canvas" aria-hidden="true">
        <div className="cronos-adaptive-visual__days">
          <span>SEG</span><span>TER</span><span>QUA</span><span>QUI</span>
        </div>
        {scheduleRows.map((row, rowIndex) => (
          <div className="cronos-adaptive-visual__row" key={`schedule-row-${rowIndex}`}>
            {row.map((state, columnIndex) => <span className={state} key={`${rowIndex}-${columnIndex}`} />)}
          </div>
        ))}
        <span className="cronos-adaptive-visual__boundary" />
      </div>
      <ol className="cronos-adaptive-visual__legend">
        {adaptiveStates.map((state, index) => (
          <li key={state.id}>
            <span className="cronos-adaptive-visual__number">0{index + 1}</span>
            <SemanticIcon name={state.icon} size="lg" />
            <div><h3>{state.title}</h3><p>{state.text}</p></div>
          </li>
        ))}
      </ol>
    </div>
  )
}
