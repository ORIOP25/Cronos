import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { CButton } from '@coreui/react'
import { useOrganization, useUser } from '@clerk/react'
import { useTutorialSimulation } from '../features/tutorial/tutorialHooks'
import { TutorialWorkspace } from '../features/tutorial/TutorialWorkspace'

function GuideLanding({ status, onOpen, onRepeat }) {
  const isInProgress = status === 'IN_PROGRESS'
  return (
    <div className="tutorial-landing" data-testid="guide-landing">
      <div className="tutorial-landing__mark">C</div>
      <p className="tutorial-eyebrow">Ambiente de demonstração</p>
      <h1>{status === 'COMPLETED' ? 'Guia concluído' : status === 'SKIPPED' ? 'Guia guardado' : 'Retomar o guia'}</h1>
      <p>{isInProgress ? 'O checkpoint está guardado apenas neste dispositivo. Pode continuar quando quiser.' : 'Pode repetir a demonstração local sem alterar dados da organização.'}</p>
      <CButton color="primary" onClick={isInProgress ? onOpen : onRepeat}>
        {isInProgress ? 'Retomar guia' : 'Repetir guia'}
      </CButton>
    </div>
  )
}

export default function Guide() {
  const navigate = useNavigate()
  const { organization } = useOrganization()
  const { user } = useUser()
  const tutorial = useTutorialSimulation({ orgId: organization?.id, userId: user?.id })
  const { isHydrated, status, startTutorial, openTutorial } = tutorial

  useEffect(() => {
    if (!isHydrated) return
    if (status === 'NOT_STARTED') startTutorial()
    else if (status === 'IN_PROGRESS') openTutorial()
  }, [isHydrated, openTutorial, startTutorial, status])

  const exitToDashboard = () => {
    tutorial.exitTutorial()
    navigate('/dashboard')
  }

  const skipToDashboard = () => {
    tutorial.skipTutorial()
    navigate('/dashboard')
  }

  const continueLater = () => {
    tutorial.continueLater()
    navigate('/dashboard')
  }

  if (!tutorial.isHydrated) return <div className="tutorial-loading" data-testid="tutorial-loading">A preparar o ambiente de demonstração…</div>
  if (tutorial.isOpen) return <TutorialWorkspace tutorial={tutorial} onExit={exitToDashboard} onSkipTutorial={skipToDashboard} onContinueLater={continueLater} />
  return <GuideLanding status={tutorial.status} onOpen={tutorial.openTutorial} onRepeat={tutorial.repeatTutorial} />
}
