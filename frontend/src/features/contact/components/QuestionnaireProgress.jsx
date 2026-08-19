import { QUESTIONNAIRE_STEP_COUNT } from '../questionnaireModel'
import GuidedFormProgress from '../../../components/GuidedFormProgress'

export default function QuestionnaireProgress({ step, pending, onBack }) {
  return <GuidedFormProgress current={step} total={QUESTIONNAIRE_STEP_COUNT} onBack={step > 1 ? onBack : undefined} backDisabled={pending} className="cronos-questionnaire__progress" trackClassName="cronos-questionnaire__track" />
}
