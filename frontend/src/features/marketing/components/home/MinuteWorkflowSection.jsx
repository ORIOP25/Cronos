import MarketingSection from '../shared/MarketingSection'
import SectionHeading from '../shared/SectionHeading'
import Reveal from '../shared/Reveal'
import MinuteDecisionVisual from './MinuteDecisionVisual'

export default function MinuteWorkflowSection() {
  return (
    <MarketingSection className="cronos-minute" labelledBy="cronos-minute-title">
      <div className="cronos-container cronos-minute__layout">
        <SectionHeading
          id="cronos-minute-title"
          eyebrow="Uma decisão curta"
          title="Resolva uma substituição em menos de 1 minuto"
          body="O fluxo acompanha a aula, a pessoa elegível e a decisão final sem espalhar o contexto."
        />
        <Reveal className="cronos-minute__experience"><MinuteDecisionVisual /></Reveal>
      </div>
    </MarketingSection>
  )
}
