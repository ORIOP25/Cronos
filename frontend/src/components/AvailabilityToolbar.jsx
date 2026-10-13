import { PREFERENCE_LEVELS } from '../constants'

const TOOL_SCORES = [2, 1, 0, -1]

export default function AvailabilityToolbar({ selectedScore, onSelect, changedCount, disabled, children }) {
  return (
    <div className="availability-toolbar" role="toolbar" aria-label="Ferramentas de disponibilidade">
      <div className="availability-toolbar__tools">
        {TOOL_SCORES.map((score) => {
          const info = PREFERENCE_LEVELS[score]
          return (
            <button
              key={score}
              type="button"
              className={`availability-tool${selectedScore === score ? ' is-selected' : ''}`}
              aria-pressed={selectedScore === score}
              onClick={() => onSelect(score)}
              disabled={disabled}
            >
              <span className="availability-tool__swatch" style={{ backgroundColor: info.color }} aria-hidden="true" />
              {info.label}
            </button>
          )
        })}
      </div>
      <div className="availability-toolbar__status" aria-live="polite">
        {changedCount} {changedCount === 1 ? 'bloco alterado' : 'blocos alterados'}
      </div>
      {children}
    </div>
  )
}
