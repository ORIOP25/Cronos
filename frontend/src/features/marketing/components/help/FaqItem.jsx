import { cilChevronBottom } from '@coreui/icons'
import CIconModule from '@coreui/icons-react'

const CIcon = CIconModule.CIcon ?? CIconModule.default ?? CIconModule

export default function FaqItem({ item, index, isOpen, onToggle }) {
  const panelId = `faq-panel-${item.id}`
  const buttonId = `faq-button-${item.id}`

  return (
    <article className={`cronos-faq__item ${isOpen ? 'is-open' : ''}`}>
      <h2>
        <button id={buttonId} type="button" aria-expanded={isOpen} aria-controls={panelId} onClick={() => onToggle(item.id)}>
          <span className="cronos-faq__number" aria-hidden="true">0{index + 1}</span>
          <span>{item.question}</span>
          <CIcon icon={cilChevronBottom} />
        </button>
      </h2>
      <div id={panelId} role="region" aria-labelledby={buttonId} className="cronos-faq__answer" aria-hidden={!isOpen}>
        <div><p>{item.answer}</p></div>
      </div>
    </article>
  )
}
