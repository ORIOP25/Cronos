import { cilArrowRight } from '@coreui/icons'
import CIcon from '@coreui/icons-react'
import TurnstileWidget from './TurnstileWidget'

export default function ContactMessageStep({ answers, website, error, pending, resetVersion, onChange, onWebsiteChange, onSubmit, onTurnstileSuccess, onTurnstileExpired, onTurnstileError }) {
  return (
    <form className="cronos-questionnaire__step" onSubmit={onSubmit}>
      <h2>Quer acrescentar algum detalhe?</h2>
      <p className="cronos-questionnaire__hint">A mensagem é opcional. Deixe-a vazia para avançar sem acrescentar detalhes.</p>
      <label className="cronos-questionnaire__field" htmlFor="message">
        <span>Mensagem, opcional</span>
        <textarea id="message" rows="5" value={answers.message} onChange={(event) => onChange('message', event.target.value)} />
      </label>
      <input className="cronos-questionnaire__honeypot" tabIndex="-1" autoComplete="off" aria-hidden="true" value={website} onChange={(event) => onWebsiteChange(event.target.value)} />
      <TurnstileWidget resetVersion={resetVersion} onSuccess={onTurnstileSuccess} onExpired={onTurnstileExpired} onError={onTurnstileError} />
      {error && <p className="cronos-questionnaire__error" role="alert">{error} <a href="mailto:contacto@cronos.pt">Contacte-nos por email.</a></p>}
      <button type="submit" className="cronos-button" disabled={pending}>
        {pending ? 'A enviar' : 'Pedir demonstração'}
        {!pending && <CIcon icon={cilArrowRight} />}
      </button>
      <p className="cronos-questionnaire__privacy">Ao enviar, o Cronos tratará os seus dados para responder ao pedido. O Cloudflare Turnstile analisa sinais técnicos para prevenir abuso e o Resend entrega a mensagem. Consulte a <a href="/privacidade">Política de Privacidade</a>.</p>
    </form>
  )
}
