import CIcon from '@coreui/icons-react'
import { cilChevronLeft } from '@coreui/icons'
import { QUESTIONNAIRE_STEP_COUNT } from '../questionnaireModel'

export default function QuestionnaireProgress({ step, pending, onBack }) {
  return <div className="cronos-questionnaire__progress"><div><span>Passo {step} de {QUESTIONNAIRE_STEP_COUNT}</span>{step > 1 && <button type="button" onClick={onBack} disabled={pending}><CIcon icon={cilChevronLeft} /> Voltar</button>}</div><div className="cronos-questionnaire__track" style={{ '--questionnaire-progress': `${step / QUESTIONNAIRE_STEP_COUNT * 100}%` }}><span /></div></div>
}
