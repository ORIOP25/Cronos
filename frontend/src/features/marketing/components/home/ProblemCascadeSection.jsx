import { problemStates } from '../../content/home'
import MarketingSection from '../shared/MarketingSection'
import SectionHeading from '../shared/SectionHeading'
import Reveal from '../shared/Reveal'

export default function ProblemCascadeSection() {
  return (
    <MarketingSection className="cronos-problem" labelledBy="cronos-problem-title">
      <div className="cronos-container cronos-problem__layout">
        <div className="cronos-problem__heading">
          <SectionHeading id="cronos-problem-title" title="Uma falta hoje não pode estragar o planeamento de junho" body="Quando um professor falta, veja imediatamente como isso afeta o cumprimento das horas e o fecho do ano letivo." />
        </div>
        <div className="cronos-problem__copy">
          <div className="cronos-problem__calendar" aria-hidden="true">
            <span className="cronos-problem__month">JUN</span>
            <span className="cronos-problem__month is-late">JUL</span>
            <span className="cronos-problem__month is-late-more">AGO</span>
            <span className="cronos-problem__drift" />
          </div>
        </div>
        <Reveal className="cronos-problem__cascade">
          <ol className="cronos-problem__timeline">
            {problemStates.map((state, index) => (
              <li key={state.id} className="cronos-problem__item">
                <span className="cronos-problem__number">0{index + 1}</span>
                <div><h3>{state.label}</h3><p>{state.detail}</p></div>
              </li>
            ))}
          </ol>
        </Reveal>
      </div>
    </MarketingSection>
  )
}
