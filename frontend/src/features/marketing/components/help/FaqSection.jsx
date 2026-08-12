import { useState } from 'react'
import MarketingSection from '../shared/MarketingSection'
import SectionHeading from '../shared/SectionHeading'
import DemoCta from '../shared/DemoCta'
import { faqItems } from '../../content/faq'
import ContactStrip from './ContactStrip'
import FaqItem from './FaqItem'

export default function FaqSection() {
  const [openId, setOpenId] = useState(null)

  const toggleQuestion = (questionId) => {
    setOpenId((currentId) => currentId === questionId ? null : questionId)
  }

  return (
    <>
      <MarketingSection className="cronos-help" labelledBy="cronos-help-title">
        <div className="cronos-container cronos-help__container">
          <div className="cronos-help__intro">
            <SectionHeading
              as="h1"
              variant="page"
              id="cronos-help-title"
              eyebrow="Ajuda"
              title="Dúvidas antes de pedir uma demonstração?"
              body="Respostas curtas para começar a conversa com a sua escola."
            />
            <div className="cronos-help__mark" aria-hidden="true"><span>?</span></div>
          </div>
          <div className="cronos-faq">
            {faqItems.map((item, index) => (
              <FaqItem key={item.id} item={item} index={index} isOpen={openId === item.id} onToggle={toggleQuestion} />
            ))}
          </div>
        </div>
      </MarketingSection>
      <ContactStrip />
      <DemoCta source="help" />
    </>
  )
}
