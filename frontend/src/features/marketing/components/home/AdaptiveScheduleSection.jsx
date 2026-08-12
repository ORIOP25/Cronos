import MarketingSection from '../shared/MarketingSection'
import SectionHeading from '../shared/SectionHeading'
import Reveal from '../shared/Reveal'
import AdaptiveScheduleVisual from './AdaptiveScheduleVisual'

export default function AdaptiveScheduleSection() {
  return (
    <MarketingSection className="cronos-adaptive" labelledBy="cronos-adaptive-title">
      <div className="cronos-container cronos-adaptive__grid">
        <div>
          <SectionHeading
            id="cronos-adaptive-title"
            title="O horário muda sem apagar o que já aconteceu"
            body="O passado e os blocos protegidos não são alterados. O Cronos reorganiza apenas o futuro editável."
          />
        </div>
        <Reveal><AdaptiveScheduleVisual /></Reveal>
      </div>
    </MarketingSection>
  )
}
