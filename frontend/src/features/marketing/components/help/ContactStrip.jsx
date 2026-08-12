import CIcon from '@coreui/icons-react'
import { cilEnvelopeClosed, cilPhone } from '@coreui/icons'
import { contactDetails } from '../../content/navigation'

const contactIcons = {
  email: cilEnvelopeClosed,
  phone: cilPhone,
}

const contactSubtitles = {
  email: 'Resposta habitual em menos de 24 horas úteis',
  phone: 'Atendimento de segunda a sexta, das 9h às 18h',
}

export default function ContactStrip() {
  return (
    <section className="cronos-contact-strip" aria-labelledby="cronos-direct-contact-title">
      <div className="cronos-container">
        <div className="cronos-contact-strip__card">
          <div className="cronos-contact-strip__header">
            <h2 id="cronos-direct-contact-title">Fale diretamente connosco</h2>
            <p>Prefere esclarecer as suas dúvidas antes de avançar? A nossa equipa está disponível para ajudar a sua escola.</p>
          </div>
          <div className="cronos-contact-strip__grid">
            {contactDetails.map((detail) => (
              <a
                key={detail.id}
                href={detail.href}
                className="cronos-contact-strip__item"
              >
                <div className="cronos-contact-strip__icon">
                  <CIcon icon={contactIcons[detail.id] || cilEnvelopeClosed} />
                </div>
                <div className="cronos-contact-strip__info">
                  <span className="cronos-contact-strip__label">{detail.label}</span>
                  <strong className="cronos-contact-strip__value">{detail.value}</strong>
                  <small className="cronos-contact-strip__sub">{contactSubtitles[detail.id]}</small>
                </div>
              </a>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
