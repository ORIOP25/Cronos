import { Link, useNavigate } from 'react-router-dom'
import { useEffect } from 'react'
import { CButton } from '@coreui/react'
import { useOrganization, useUser } from '@clerk/react'
import { useSearchParams } from 'react-router-dom'
import { useTutorialSimulation } from '../features/tutorial/tutorialHooks'
import { TutorialWorkspace } from '../features/tutorial/TutorialWorkspace'
import { TUTORIAL_COPY } from '../features/tutorial/tutorialContent'
import { publicAsset } from '../utils/publicAsset'

function GuideLanding({ status, onStart, onOpen, onRepeat }) {
  const isNew = status === 'NOT_STARTED'
  const isInProgress = status === 'IN_PROGRESS'
  const title = isNew ? 'Conhecer o guia' : isInProgress ? 'Retomar o guia' : status === 'COMPLETED' ? 'Guia concluído' : 'Guia guardado'
  const description = isNew
    ? 'Conheça as funcionalidades que acompanham a preparação e a semana da escola.'
    : isInProgress
      ? 'O seu progresso está guardado. Pode continuar de onde ficou.'
      : status === 'COMPLETED'
        ? TUTORIAL_COPY.completion
      : 'Pode voltar à escola ou repetir o guia para rever os passos.'
  const action = isNew ? onStart : isInProgress ? onOpen : onRepeat

  return (
    <div className="tutorial-landing" data-testid="guide-landing">
      <img
        className="tutorial-landing__logo"
        src={publicAsset('/logo.png')}
        alt="Cronos"
        width="62"
        height="62"
        decoding="async"
      />
      <p className="tutorial-eyebrow">Ambiente de demonstração</p>
      <h1>{title}</h1>
      <p>{description}</p>
      <CButton color="primary" onClick={action}>{isNew ? 'Conhecer o guia' : isInProgress ? 'Retomar guia' : 'Repetir guia'}</CButton>
      <Link className="btn btn-link" to="/dashboard">Voltar à escola</Link>
    </div>
  )
}

export default function Guide() {
  const navigate = useNavigate()
  const { organization } = useOrganization()
  const { user } = useUser()
  const tutorial = useTutorialSimulation({ orgId: organization?.id, userId: user?.id })
  const [searchParams] = useSearchParams()
  const entry = searchParams.get('entry')
  const {
    isHydrated,
    isOpen,
    status,
    startTutorial,
    openTutorial,
    repeatTutorial,
  } = tutorial

  useEffect(() => {
    if (!isHydrated || isOpen || !entry) return
    if (entry === 'start' && status === 'NOT_STARTED') startTutorial()
    if (entry === 'resume' && status === 'IN_PROGRESS') openTutorial()
    if (entry === 'repeat' && ['COMPLETED', 'SKIPPED'].includes(status)) repeatTutorial()
  }, [entry, isHydrated, isOpen, openTutorial, repeatTutorial, startTutorial, status])

  const exitToDashboard = () => {
    tutorial.exitTutorial()
    navigate('/dashboard')
  }

  const skipToDashboard = () => {
    tutorial.skipTutorial()
    navigate('/dashboard')
  }

  if (!isHydrated) return <div className="tutorial-loading" data-testid="tutorial-loading">A preparar o ambiente de demonstração…</div>
  if (isOpen) return <TutorialWorkspace tutorial={tutorial} onExit={exitToDashboard} onSkipTutorial={skipToDashboard} />
  return <GuideLanding status={tutorial.status} onStart={tutorial.startTutorial} onOpen={tutorial.openTutorial} onRepeat={tutorial.repeatTutorial} />
}
