import { useState, memo } from 'react'
import CIcon from '@coreui/icons-react'
import { cilArrowRight, cilChevronLeft, cilCheckCircle } from '@coreui/icons'
import { contactCards } from '../../data/marketingData'

const ContactQuestionnaire = memo(function ContactQuestionnaire() {
  const [contactStep, setContactStep] = useState(0)
  const [contactData, setContactData] = useState({
    subject: '',
    courses: '',
    teachers: '',
    name: '',
    email: '',
    phone: '',
    message: '',
  })

  const handleSelectSubject = (val) => {
    setContactData((prev) => ({ ...prev, subject: val }))
    setContactStep(2)
  }

  const handleSelectCourses = (val) => {
    setContactData((prev) => ({ ...prev, courses: val }))
    setContactStep(3)
  }

  const handleSelectTeachers = (val) => {
    setContactData((prev) => ({ ...prev, teachers: val }))
    setContactStep(4)
  }

  const handleContactDetailsNext = (e) => {
    e.preventDefault()
    if (!contactData.name || !contactData.email) return
    setContactStep(5)
  }

  const handleFinalSubmit = (e) => {
    if (e) e.preventDefault()
    setContactStep(6)
  }

  return (
    <section className="cronos-contact" id="contacto" aria-labelledby="cronos-contact-title">
      <div className="cronos-layout cronos-contact__grid">
        <div className="cronos-contact__content">
          <h2 id="cronos-contact-title">
            Gostava de ver como funcionaria na sua escola? <br />
            <span className="cronos-contact-title-highlight">Fale connosco!</span>
          </h2>
          <p>
            Sem compromisso. Mostre-nos o seu maior desafio com os horários atuais e mostramos-lhe, em 15 minutos, como o Cronos pode ajudar a resolvê-lo.
          </p>

          <div className="cronos-contact-cards">
            {contactCards.map((card) => (
              <div className="cronos-contact-card" key={card.label}>
                <span className="cronos-contact-card__icon">
                  <CIcon icon={card.icon} />
                </span>
                <div>
                  <strong>{card.label}</strong>
                  <span>{card.value}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Multi-Step Interactive Questionnaire Panel */}
        <div className="cronos-contact-interactive-panel">
          {contactStep > 0 && contactStep < 6 && (
            <div className="cronos-contact-progress">
              <div className="cronos-contact-progress__header">
                <span className="cronos-contact-progress__step">Passo {contactStep} de 5</span>
                {contactStep > 1 && (
                  <button
                    type="button"
                    className="cronos-contact-back-btn"
                    onClick={() => setContactStep((prev) => prev - 1)}
                  >
                    <CIcon icon={cilChevronLeft} /> Voltar
                  </button>
                )}
              </div>
              <div className="cronos-contact-progress__track">
                <div
                  className="cronos-contact-progress__fill"
                  style={{ width: `${(contactStep / 5) * 100}%` }}
                />
              </div>
            </div>
          )}

          {/* Step 0: Welcome */}
          {contactStep === 0 && (
            <div className="cronos-contact-step cronos-contact-step--welcome">
              <h3>Pronto para simplificar a gestão de horários da sua escola?</h3>
              <p>
                Responda a 4 perguntas rápidas para personalizarmos a conversa com a nossa equipa.
              </p>
              <button
                type="button"
                className="cronos-button cronos-button--form"
                onClick={() => setContactStep(1)}
              >
                Falar com a nossa equipa <CIcon icon={cilArrowRight} />
              </button>
              <p className="cronos-form__note">Demora menos de 1 minuto. Sem qualquer compromisso.</p>
            </div>
          )}

          {/* Step 1: Subject */}
          {contactStep === 1 && (
            <div className="cronos-contact-step">
              <h3>Como podemos ajudar?</h3>
              <div className="cronos-contact-options-grid">
                <button
                  type="button"
                  className="cronos-contact-option-card cronos-contact-option-card--featured"
                  onClick={() => handleSelectSubject('Criar horários do zero sem conflitos')}
                >
                  <strong>Criar horários do zero sem conflitos</strong>
                  <span>Gerar a grelha completa automaticamente com salas e professores</span>
                </button>
                <button
                  type="button"
                  className="cronos-contact-option-card cronos-contact-option-card--featured"
                  onClick={() => handleSelectSubject('Gerir furos, faltas e substituições')}
                >
                  <strong>Gerir furos, faltas e substituições</strong>
                  <span>Resolver imprevistos diários sem desmoronar o calendário</span>
                </button>
                <button
                  type="button"
                  className="cronos-contact-option-card cronos-contact-option-card--featured"
                  onClick={() => handleSelectSubject('Acompanhar horas de UFCDs e módulos')}
                >
                  <strong>Acompanhar horas de UFCDs e módulos</strong>
                  <span>Controlo transparente do progresso letivo e sumários</span>
                </button>
                <button
                  type="button"
                  className="cronos-contact-option-card cronos-contact-option-card--subtle"
                  onClick={() => handleSelectSubject('Outro')}
                >
                  <strong>Outro</strong>
                  <span>Outra necessidade ou questão específica</span>
                </button>
              </div>
            </div>
          )}

          {/* Step 2: Courses */}
          {contactStep === 2 && (
            <div className="cronos-contact-step">
              <h3>Quantos cursos leciona a sua escola?</h3>
              <div className="cronos-contact-options-list">
                {['Entre 1 e 5', 'Entre 5 e 20', '20+'].map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    className="cronos-contact-option-card"
                    onClick={() => handleSelectCourses(opt)}
                  >
                    <strong>{opt}</strong>
                    <span>Cursos profissionais lecionados na escola</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Step 3: Teachers */}
          {contactStep === 3 && (
            <div className="cronos-contact-step">
              <h3>Quantos professores integram o seu corpo docente?</h3>
              <div className="cronos-contact-options-list">
                {['Entre 1 e 15', 'Entre 15 e 50', '50+'].map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    className="cronos-contact-option-card"
                    onClick={() => handleSelectTeachers(opt)}
                  >
                    <strong>{opt}</strong>
                    <span>Docentes e formadores ativos no corpo docente</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Step 4: Contact details */}
          {contactStep === 4 && (
            <form className="cronos-contact-step" onSubmit={handleContactDetailsNext}>
              <h3>Dados de contacto</h3>
              <div className="cronos-contact-fields">
                <label className="cronos-field cronos-field--full">
                  <span>O seu nome *</span>
                  <input
                    type="text"
                    required
                    placeholder="Nome completo"
                    value={contactData.name}
                    onChange={(e) => setContactData({ ...contactData, name: e.target.value })}
                  />
                </label>
                <label className="cronos-field cronos-field--full">
                  <span>Endereço de email *</span>
                  <input
                    type="email"
                    required
                    placeholder="exemplo@escola.pt"
                    value={contactData.email}
                    onChange={(e) => setContactData({ ...contactData, email: e.target.value })}
                  />
                </label>
                <label className="cronos-field cronos-field--full">
                  <span>Número de telefone</span>
                  <input
                    type="tel"
                    placeholder="+351 912 345 678"
                    value={contactData.phone}
                    onChange={(e) => setContactData({ ...contactData, phone: e.target.value })}
                  />
                </label>
              </div>
              <button type="submit" className="cronos-button cronos-button--form">
                Seguinte <CIcon icon={cilArrowRight} />
              </button>
            </form>
          )}

          {/* Step 5: Final message */}
          {contactStep === 5 && (
            <div className="cronos-contact-step">
              <h3>Mais algum detalhe a partilhar?</h3>
              <textarea
                className="cronos-contact-textarea"
                placeholder="Escreva aqui qualquer detalhe adicional..."
                rows="4"
                value={contactData.message}
                onChange={(e) => setContactData({ ...contactData, message: e.target.value })}
              />
              <div className="cronos-contact-step-actions">
                <button
                  type="button"
                  className="cronos-button cronos-button--secondary"
                  onClick={() => handleFinalSubmit()}
                >
                  Não, obrigado
                </button>
                <button
                  type="button"
                  className="cronos-button"
                  onClick={() => handleFinalSubmit()}
                >
                  Enviar <CIcon icon={cilArrowRight} />
                </button>
              </div>
            </div>
          )}

          {/* Step 6: Confirmation Screen */}
          {contactStep === 6 && (
            <div className="cronos-contact-step cronos-contact-step--success">
              <div className="cronos-contact-success-icon">
                <CIcon icon={cilCheckCircle} size="xl" />
              </div>
              <h3>Obrigado pelo contacto, {contactData.name || 'de toda a equipa'}!</h3>
              <p className="cronos-contact-success__sub">Recebemos os seus dados.</p>
              <p className="cronos-contact-success__detail">
                Entraremos em contacto para o email{' '}
                <strong>{contactData.email}</strong> em menos de 24 horas.
              </p>
              <button
                type="button"
                className="cronos-button cronos-button--secondary"
                onClick={() => {
                  setContactStep(0)
                  setContactData({ subject: '', courses: '', teachers: '', name: '', email: '', phone: '', message: '' })
                }}
              >
                Voltar ao início
              </button>
            </div>
          )}
        </div>
      </div>
    </section>
  )
})

export default ContactQuestionnaire
