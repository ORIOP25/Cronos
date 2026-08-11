import { memo, useCallback, useEffect, useRef, useState } from 'react'
import CIcon from '@coreui/icons-react'
import { cilArrowRight, cilCheckCircle, cilChevronLeft } from '@coreui/icons'
import { contactCards } from '../../data/marketingData'
import { useSubmitContact } from '../../features/contact/data'
import { getApiErrorMessage } from '../../utils/apiErrors'

const SUBJECT_OPTIONS = [
  'Criar horários do zero sem conflitos',
  'Gerir furos, faltas e substituições',
  'Acompanhar horas de UFCDs e módulos',
  'Outro',
]
const COURSE_OPTIONS = ['Entre 1 e 5', 'Entre 5 e 20', '20+']
const TEACHER_OPTIONS = ['Entre 1 e 15', 'Entre 15 e 50', '50+']
const EMPTY_CONTACT = { subject: '', courses: '', teachers: '', name: '', email: '', phone: '', message: '' }
const TURNSTILE_POLL_INTERVAL_MS = 50
const TURNSTILE_LOAD_TIMEOUT_MS = 3000

const ContactQuestionnaire = memo(function ContactQuestionnaire() {
  const [contactStep, setContactStep] = useState(0)
  const [contactData, setContactData] = useState(EMPTY_CONTACT)
  const [website, setWebsite] = useState('')
  const [turnstileToken, setTurnstileToken] = useState('')
  const [turnstileResetVersion, setTurnstileResetVersion] = useState(0)
  const [submitError, setSubmitError] = useState('')
  const [successName, setSuccessName] = useState('')
  const submitContact = useSubmitContact()

  const handleTurnstileSuccess = useCallback((token) => {
    setTurnstileToken(token)
    setSubmitError('')
  }, [])
  const handleTurnstileExpired = useCallback(() => setTurnstileToken(''), [])
  const handleTurnstileError = useCallback(() => {
    setTurnstileToken('')
    setSubmitError('Não foi possível concluir a verificação anti-spam.')
  }, [])

  const updateContactData = (field, value) => setContactData((current) => ({ ...current, [field]: value }))
  const selectSubject = (value) => { updateContactData('subject', value); setContactStep(2) }
  const selectCourses = (value) => { updateContactData('courses', value); setContactStep(3) }
  const selectTeachers = (value) => { updateContactData('teachers', value); setContactStep(4) }
  const handleContactDetailsNext = (event) => { event.preventDefault(); setContactStep(5) }
  const handleBack = () => {
    if (contactStep === 5) setTurnstileToken('')
    setContactStep((step) => step - 1)
  }
  const handleFinalSubmit = async (event) => {
    event.preventDefault()
    if (submitContact.isPending) return
    setSubmitError('')
    if (!turnstileToken) {
      setSubmitError('Confirme a verificação anti-spam antes de enviar o pedido.')
      return
    }
    try {
      await submitContact.mutateAsync({ ...contactData, website, turnstile_token: turnstileToken })
      setSuccessName(contactData.name)
      setContactData(EMPTY_CONTACT)
      setWebsite('')
      setTurnstileToken('')
      setContactStep(6)
    } catch (error) {
      setTurnstileToken('')
      setTurnstileResetVersion((version) => version + 1)
      setSubmitError(getApiErrorMessage(error, 'Não foi possível enviar o pedido neste momento.'))
    }
  }
  const resetQuestionnaire = () => {
    setContactStep(0)
    setContactData(EMPTY_CONTACT)
    setWebsite('')
    setTurnstileToken('')
    setSuccessName('')
    setSubmitError('')
    submitContact.reset()
  }

  return (
    <section className="cronos-contact" id="contacto" aria-labelledby="cronos-contact-title">
      <div className="cronos-layout cronos-contact__grid">
        <div className="cronos-contact__content">
          <h2 id="cronos-contact-title">Gostava de ver como funcionaria na sua escola? <br /><span className="cronos-contact-title-highlight">Fale connosco!</span></h2>
          <p>Sem compromisso. Mostre-nos o seu maior desafio com os horários atuais e mostramos-lhe como o Cronos pode ajudar.</p>
          <div className="cronos-contact-cards">
            {contactCards.map((card) => <div className="cronos-contact-card" key={card.label}><span className="cronos-contact-card__icon"><CIcon icon={card.icon} /></span><div><strong>{card.label}</strong><span>{card.value}</span></div></div>)}
          </div>
        </div>
        <div className="cronos-contact-interactive-panel">
          {contactStep > 0 && contactStep < 6 && <Progress step={contactStep} pending={submitContact.isPending} onBack={handleBack} />}
          {contactStep === 0 && <Welcome onStart={() => setContactStep(1)} />}
          {contactStep === 1 && <Options title="Como podemos ajudar?" options={SUBJECT_OPTIONS} onSelect={selectSubject} />}
          {contactStep === 2 && <Options title="Quantos cursos leciona a sua escola?" options={COURSE_OPTIONS} onSelect={selectCourses} />}
          {contactStep === 3 && <Options title="Quantos professores integram o seu corpo docente?" options={TEACHER_OPTIONS} onSelect={selectTeachers} />}
          {contactStep === 4 && <ContactDetails data={contactData} onChange={updateContactData} onSubmit={handleContactDetailsNext} />}
          {contactStep === 5 && <FinalForm data={contactData} website={website} error={submitError} pending={submitContact.isPending} resetVersion={turnstileResetVersion} onChange={updateContactData} onWebsiteChange={setWebsite} onSubmit={handleFinalSubmit} onTurnstileSuccess={handleTurnstileSuccess} onTurnstileExpired={handleTurnstileExpired} onTurnstileError={handleTurnstileError} />}
          {contactStep === 6 && <Success name={successName} onReset={resetQuestionnaire} />}
        </div>
      </div>
    </section>
  )
})

function Progress({ step, pending, onBack }) { return <div className="cronos-contact-progress"><div className="cronos-contact-progress__header"><span className="cronos-contact-progress__step">Passo {step} de 5</span>{step > 1 && <button type="button" className="cronos-contact-back-btn" disabled={pending} onClick={onBack}><CIcon icon={cilChevronLeft} /> Voltar</button>}</div><div className="cronos-contact-progress__track"><div className="cronos-contact-progress__fill" style={{ width: `${step / 5 * 100}%` }} /></div></div> }
function Welcome({ onStart }) { return <div className="cronos-contact-step cronos-contact-step--welcome"><h3>Pronto para simplificar a gestão de horários da sua escola?</h3><p>Responda a 4 perguntas rápidas para personalizarmos a conversa.</p><button type="button" className="cronos-button cronos-button--form" onClick={onStart}>Falar com a nossa equipa <CIcon icon={cilArrowRight} /></button></div> }
function Options({ title, options, onSelect }) { return <div className="cronos-contact-step"><h3>{title}</h3><div className="cronos-contact-options-list">{options.map((option) => <button key={option} type="button" className="cronos-contact-option-card" onClick={() => onSelect(option)}><strong>{option}</strong></button>)}</div></div> }
function ContactDetails({ data, onChange, onSubmit }) {
  return (
    <form className="cronos-contact-step" onSubmit={onSubmit}>
      <h3>Dados de contacto</h3>
      <div className="cronos-contact-fields">
        <Field label="O seu nome *" type="text" required placeholder="Ex: Maria Santos" value={data.name} onChange={(value) => onChange('name', value)} />
        <Field label="Endereço de email *" type="email" required placeholder="maria.santos@escola.pt" value={data.email} onChange={(value) => onChange('email', value)} />
        <Field label="Número de telefone" type="tel" placeholder="+351 912 345 678" value={data.phone} onChange={(value) => onChange('phone', value)} />
      </div>
      <button type="submit" className="cronos-button cronos-button--form">Seguinte <CIcon icon={cilArrowRight} /></button>
    </form>
  )
}
function Field({ label, type, required = false, placeholder, value, onChange }) {
  return <label className="cronos-field"><span>{label}</span><input type={type} required={required} placeholder={placeholder} value={value} onChange={(event) => onChange(event.target.value)} /></label>
}
function FinalForm({ data, website, error, pending, resetVersion, onChange, onWebsiteChange, onSubmit, onTurnstileSuccess, onTurnstileExpired, onTurnstileError }) {
  return (
    <form className="cronos-contact-step" onSubmit={onSubmit}>
      <h3>Mais algum detalhe a partilhar?</h3>
      <textarea className="cronos-contact-textarea" placeholder="Escreva aqui qualquer detalhe adicional..." rows="4" value={data.message} onChange={(event) => onChange('message', event.target.value)} />
      <input className="cronos-contact-honeypot" name="website" tabIndex={-1} autoComplete="off" aria-hidden="true" value={website} onChange={(event) => onWebsiteChange(event.target.value)} />
      <Turnstile resetVersion={resetVersion} onSuccess={onTurnstileSuccess} onExpired={onTurnstileExpired} onError={onTurnstileError} />
      {error && <p className="cronos-contact-error" role="alert">{error} Tente novamente ou contacte-nos por <a href="mailto:contacto@cronos.pt">email</a>.</p>}
      <div className="cronos-contact-step-actions">
        <button type="submit" className="cronos-button cronos-button--secondary" disabled={pending}>Não, obrigado</button>
        <button type="submit" className="cronos-button" disabled={pending}>{pending ? 'A enviar…' : 'Enviar'} <CIcon icon={cilArrowRight} /></button>
      </div>
      <p className="cronos-contact-privacy">Ao enviar, os dados indicados serão usados apenas para responder ao seu pedido e não serão utilizados para marketing.</p>
    </form>
  )
}
function Turnstile({ resetVersion, onSuccess, onExpired, onError }) {
  const element = useRef(null)
  const widgetId = useRef(null)
  const [loadError, setLoadError] = useState(false)
  useEffect(() => {
    let pollId
    let timeoutId
    let disposed = false
    const siteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY
    const clearLoadingTimers = () => {
      if (pollId) window.clearInterval(pollId)
      if (timeoutId) window.clearTimeout(timeoutId)
    }
    const renderWidget = () => {
      if (disposed || widgetId.current !== null || !element.current || !siteKey || !window.turnstile?.render) return false
      widgetId.current = window.turnstile.render(element.current, {
        sitekey: siteKey,
        action: 'contact',
        callback: onSuccess,
        'expired-callback': onExpired,
        'error-callback': onError,
      })
      setLoadError(false)
      clearLoadingTimers()
      return true
    }

    if (!siteKey) {
      timeoutId = window.setTimeout(() => {
        if (!disposed) setLoadError(true)
      }, 0)
    } else if (!renderWidget()) {
      pollId = window.setInterval(renderWidget, TURNSTILE_POLL_INTERVAL_MS)
      timeoutId = window.setTimeout(() => {
        clearLoadingTimers()
        if (!disposed && widgetId.current === null) setLoadError(true)
      }, TURNSTILE_LOAD_TIMEOUT_MS)
    }
    return () => {
      disposed = true
      clearLoadingTimers()
      if (widgetId.current !== null) window.turnstile?.remove?.(widgetId.current)
      widgetId.current = null
    }
  }, [onError, onExpired, onSuccess])
  useEffect(() => {
    if (resetVersion > 0 && widgetId.current !== null) window.turnstile?.reset?.(widgetId.current)
  }, [resetVersion])
  return <>
    <div ref={element} className="cronos-turnstile" />
    {loadError && <p className="cronos-contact-error" role="alert">NÃ£o foi possÃ­vel carregar a verificaÃ§Ã£o anti-spam. Tente atualizar a pÃ¡gina.</p>}
  </>
}

function Success({ name, onReset }) { return <div className="cronos-contact-step cronos-contact-step--success"><div className="cronos-contact-success-icon"><CIcon icon={cilCheckCircle} size="xl" /></div><h3>Obrigado pelo contacto, {name || 'de toda a equipa'}!</h3><p className="cronos-contact-success__detail">Responderemos assim que possível para o email indicado.</p><button type="button" className="cronos-button cronos-button--secondary" onClick={onReset}>Voltar ao início</button></div> }

export default ContactQuestionnaire
