import QuestionnaireOptionStep from './QuestionnaireOptionStep'
import ContactDetailsStep from './ContactDetailsStep'
import ContactMessageStep from './ContactMessageStep'
import { questionnaireOptions } from '../content'

export default function QuestionnaireStep({ step, answers, errors, state, callbacks }) {
  switch (step) {
    case 1:
      return <QuestionnaireOptionStep title="Qual é o principal desafio da sua escola?" field="subject" options={questionnaireOptions.subject} value={answers.subject} errors={errors} onSelect={callbacks.onOption} />
    case 2:
      return <QuestionnaireOptionStep title="Quantos cursos leciona a sua escola?" field="courses" options={questionnaireOptions.courses} value={answers.courses} errors={errors} onSelect={callbacks.onOption} />
    case 3:
      return <QuestionnaireOptionStep title="Quantos professores integram a sua escola?" field="teachers" options={questionnaireOptions.teachers} value={answers.teachers} errors={errors} onSelect={callbacks.onOption} />
    case 4:
      return <ContactDetailsStep answers={answers} errors={errors} onChange={callbacks.onChange} onNext={callbacks.onDetailsNext} />
    case 5:
      return <ContactMessageStep answers={answers} website={answers.website} error={state.error} pending={state.status === 'submitting'} resetVersion={state.turnstileResetVersion} onChange={callbacks.onChange} onWebsiteChange={callbacks.onWebsiteChange} onSubmit={callbacks.onSubmit} onTurnstileSuccess={callbacks.onTurnstileSuccess} onTurnstileExpired={callbacks.onTurnstileExpired} onTurnstileError={callbacks.onTurnstileError} />
    default:
      return null
  }
}
