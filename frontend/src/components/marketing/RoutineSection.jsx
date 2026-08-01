import { useState, memo } from 'react'
import CIcon from '@coreui/icons-react'
import { cilCheck } from '@coreui/icons'
import { routineChapters } from '../../data/marketingData'

const RoutineSection = memo(function RoutineSection() {
  const [activeRoutine, setActiveRoutine] = useState(0)
  const currentRoutine = routineChapters[activeRoutine]

  return (
    <section className="cronos-routine" id="rotina" aria-labelledby="cronos-routine-title">
      <div className="cronos-layout">
        <div className="cronos-section-heading cronos-section-heading--split">
          <h2 id="cronos-routine-title">A semana letiva</h2>
          <p>
            Seguimos uma semana real numa escola profissional: o que se prepara, o que se publica, o que muda e o que fica registado para a direção acompanhar.
          </p>
        </div>

        <div className="cronos-routine-stream">
          {routineChapters.map((chapter, idx) => (
            <button
              key={chapter.moment}
              type="button"
              className={`cronos-routine-stream-pill ${idx === activeRoutine ? 'is-active' : ''}`}
              onClick={() => setActiveRoutine(idx)}
            >
              <span className="cronos-stream-num">0{idx + 1}</span>
              <span className="cronos-stream-label">{chapter.moment}</span>
            </button>
          ))}
        </div>

        <article className="cronos-routine-canvas">
          <div className="cronos-routine-canvas__story">
            <h3>{currentRoutine.title}</h3>
            <p>{currentRoutine.story}</p>
          </div>
          <div className="cronos-routine-canvas__checklist">
            <h4>{currentRoutine.detailTitle}</h4>
            <ul className="cronos-routine-list">
              {currentRoutine.items.map((item) => (
                <li key={item}>
                  <CIcon icon={cilCheck} className="cronos-check-icon" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </article>
      </div>
    </section>
  )
})

export default RoutineSection
