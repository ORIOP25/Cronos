import { useEffect, useReducer } from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { TutorialWorkspace } from '../features/tutorial/TutorialWorkspace'
import { TutorialInteractionGuard } from '../features/tutorial/TutorialInteractionGuard'
import { TutorialApiBoundary } from '../features/tutorial/TutorialApiBoundary'
import { useApiClient } from '../ApiClientContext'
import { TUTORIAL_STEPS } from '../features/tutorial/tutorialContent'
import { INITIAL_TUTORIAL_STATE, applyTutorialTransition } from '../features/tutorial/tutorialModel'
import { createTutorialScenario } from '../features/tutorial/tutorialScenario'
import { renderWithRouter } from './testUtils'

function makeTutorial(state) {
  const currentStepIndex = TUTORIAL_STEPS.findIndex((step) => step.id === state.stepId)
  return {
    storageKey: 'cronos:tutorial:v3:user:test:org:test',
    isOpen: true,
    version: 3,
    status: state.status,
    tutorialRunId: state.tutorialRunId,
    stepId: state.stepId,
    currentStep: TUTORIAL_STEPS[currentStepIndex],
    currentStepIndex,
    totalSteps: TUTORIAL_STEPS.length,
    progressPercent: Math.round((currentStepIndex / TUTORIAL_STEPS.length) * 100),
    persistenceError: null,
    versionUpdateVisible: false,
    dismissVersionUpdate: vi.fn(),
    advanceTutorial: vi.fn(),
  }
}

function InteractiveTutorial({ stepId = 'curriculum' }) {
  const [state, dispatch] = useReducer(applyTutorialTransition, {
    ...INITIAL_TUTORIAL_STATE,
    status: 'IN_PROGRESS',
    tutorialRunId: 'run-workspace',
    stepId,
  })
  const tutorial = makeTutorial(state)
  tutorial.advanceTutorial = (expectedStepId) => dispatch({ type: 'ADVANCE', expectedStepId })
  return <TutorialWorkspace tutorial={tutorial} onExit={vi.fn()} onSkipTutorial={vi.fn()} />
}

describe('TutorialWorkspace v3', () => {
  it('keeps one local API client bound to the current presented scenario', async () => {
    const clients = []
    function Probe() {
      const client = useApiClient()
      useEffect(() => { clients.push(client) }, [client])
      return null
    }
    const before = createTutorialScenario('schedule')
    const after = createTutorialScenario('recovery')
    const { rerender } = render(<TutorialApiBoundary stepId="schedule" scenario={before}><Probe /></TutorialApiBoundary>)
    await waitFor(() => expect(clients).toHaveLength(1))
    expect(await clients[0].get('/scheduler/drafts/current')).toBeNull()
    rerender(<TutorialApiBoundary stepId="recovery" scenario={after}><Probe /></TutorialApiBoundary>)
    await waitFor(() => expect(clients).toHaveLength(2))
    expect(await clients[1].get('/scheduler/drafts/current')).toMatchObject({
      status: 'PENDING',
      strategy: 'ADAPTIVE_REPAIR',
      metrics: { disruption_cost: 2 },
    })
  })

  it('advances only from the instruction panel with the current expected step', async () => {
    renderWithRouter(<InteractiveTutorial />)
    expect(await screen.findByTestId('tutorial-step-counter')).toHaveTextContent('Passo 1 de 13')
    expect(screen.getByTestId('tutorial-initial-note')).toHaveTextContent(/cada passo apresenta um exemplo preparado/i)
    fireEvent.click(screen.getByTestId('tutorial-advance-button'))
    await waitFor(() => expect(screen.getByTestId('tutorial-step-counter')).toHaveTextContent('Passo 2 de 13'))
  })

  it('renders the schedule step with generation available and approval disabled until a draft exists', async () => {
    renderWithRouter(<InteractiveTutorial stepId="schedule" />)
    const page = within(document.querySelector('.tutorial-live-page'))
    expect(await screen.findByRole('heading', { name: 'Horários Escolares' })).toBeVisible()
    expect(await page.findByRole('button', { name: /gerar horário/i })).toBeEnabled()
    expect(page.queryByRole('button', { name: 'Aprovar' })).not.toBeInTheDocument()
  }, 15_000)

  it('opens a previous step as a readable, non-mutating review', async () => {
    renderWithRouter(<InteractiveTutorial stepId="courses_classes" />)
    fireEvent.click(await screen.findByTestId('tutorial-prev-button'))
    await waitFor(() => expect(screen.getByText(/a rever o passo 1/i)).toBeVisible())
    expect(document.querySelector('.tutorial-live-page')).toHaveClass('is-reviewing')
    expect(document.querySelector('.tutorial-live-page')).not.toHaveAttribute('aria-hidden')
    expect(document.querySelector('.tutorial-live-page')).not.toHaveAttribute('inert')
    const consultButton = await screen.findByRole('button', { name: /consultar programação/i })
    expect(consultButton).toBeVisible()
    fireEvent.click(consultButton)
    expect(screen.getByRole('dialog')).toHaveTextContent('Fundamentos de programação')
    expect(screen.getByLabelText(/nome da disciplina/i)).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /voltar ao passo atual/i }))
    await waitFor(() => expect(document.querySelector('[data-tutorial-target="edit-class-1"]')).toBeEnabled())
  }, 15_000)

  it('keeps the interaction guard scoped to the active feature target', () => {
    const onTarget = vi.fn()
    const onOther = vi.fn()
    render(
      <>
        <TutorialInteractionGuard step={TUTORIAL_STEPS[0]} />
        <button type="button" data-tutorial-target="edit-record-1" onClick={onTarget}>Editar Programação</button>
        <button type="button" onClick={onOther}>Apagar dados</button>
      </>,
    )
    fireEvent.click(screen.getByRole('button', { name: /editar programação/i }))
    fireEvent.click(screen.getByRole('button', { name: /apagar dados/i }))
    expect(onTarget).toHaveBeenCalledOnce()
    expect(onOther).not.toHaveBeenCalled()
  })
})
