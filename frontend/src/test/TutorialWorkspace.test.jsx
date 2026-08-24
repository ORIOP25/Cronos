import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { TutorialWorkspace } from '../features/tutorial/TutorialWorkspace'
import { TutorialInteractionGuard } from '../features/tutorial/TutorialInteractionGuard'
import { TUTORIAL_STEPS } from '../features/tutorial/tutorialScenario'
import { INITIAL_TUTORIAL_STATE, applyTutorialTransition, getTutorialScenario } from '../features/tutorial/tutorialModel'
import { renderWithRouter } from './testUtils'

function makeTutorial(state, onAction = vi.fn()) {
  const currentStepIndex = TUTORIAL_STEPS.findIndex((step) => step.id === state.stepId)
  return {
    isOpen: true,
    stepId: state.stepId,
    currentStep: TUTORIAL_STEPS[currentStepIndex],
    currentStepIndex,
    totalSteps: TUTORIAL_STEPS.length,
    progressPercent: Math.round(((currentStepIndex + 1) / TUTORIAL_STEPS.length) * 100),
    scenario: getTutorialScenario(state),
    onAction,
    completeActionSequence: vi.fn(),
    skipStep: vi.fn(),
  }
}

async function expectCheckpointPageReady(step) {
  if (step.id === 'structure_overview') {
    expect(await screen.findByTestId('preparation-dashboard')).toBeVisible()
    return
  }
  if (['subject_create', 'module_add', 'assignment_create'].includes(step.id)) {
    expect((await screen.findAllByText('Programação')).length).toBeGreaterThan(0)
    return
  }
  if (['course_create', 'class_create'].includes(step.id)) {
    expect((await screen.findAllByText('Técnico de Informática')).length).toBeGreaterThan(0)
    return
  }
  if (['teacher_add', 'teacher_competency'].includes(step.id)) {
    expect((await screen.findAllByText('Prof. António Silva')).length).toBeGreaterThan(0)
    return
  }
  if (step.id === 'room_add') {
    expect(await screen.findByText('Sala 101')).toBeVisible()
    return
  }
  if (step.id === 'availability_review') {
    expect((await screen.findAllByRole('button', { name: /neutro/i }, { timeout: 5_000 })).length).toBeGreaterThan(0)
    return
  }
  if (['substitute_teacher_select', 'substitute_subject_select', 'substitution_complete'].includes(step.id)) {
    expect(await screen.findByRole('button', { name: /decidir/i })).toBeEnabled()
    return
  }
  if (step.id === 'debt_observe') {
    expect((await screen.findAllByText('Prof. António Silva')).length).toBeGreaterThan(0)
    return
  }
  expect((await screen.findAllByText('Programação')).length).toBeGreaterThan(0)
}

describe('TutorialWorkspace', () => {
  it('observes a target interaction even when the real component stops bubbling', async () => {
    const onTargetAction = vi.fn()
    const step = TUTORIAL_STEPS.find(({ id }) => id === 'substitute_teacher_select')

    render(
      <>
        <TutorialInteractionGuard step={step} reviewMode={false} onTargetAction={onTargetAction} />
        <button type="button" data-tutorial-target="decision-open" onClick={(event) => event.stopPropagation()}>Decidir</button>
      </>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Decidir' }))
    await waitFor(() => expect(onTargetAction).toHaveBeenCalledOnce())
  })

  it('renders and highlights the real Cronos page instead of a tutorial copy', async () => {
    let state = applyTutorialTransition(INITIAL_TUTORIAL_STATE, { type: 'START', tutorialRunId: 'run-view' })
    state = applyTutorialTransition(state, { type: 'COMPLETE_STEP', actionId: 'continue' })
    const onAction = vi.fn()

    renderWithRouter(<TutorialWorkspace tutorial={makeTutorial(state, onAction)} onExit={vi.fn()} onSkipTutorial={vi.fn()} onContinueLater={vi.fn()} />)

    expect(await screen.findByRole('heading', { name: 'Disciplinas' })).toBeVisible()
    const realCreateButton = screen.getByRole('button', { name: /nova disciplina/i })
    expect(document.querySelector('.tutorial-target-highlight')).not.toBeInTheDocument()
    expect(document.querySelector('.tutorial-screen')).not.toBeInTheDocument()

    fireEvent.click(realCreateButton)
    const dialog = await screen.findByRole('dialog')
    await waitFor(() => expect(document.querySelector('.tutorial-target-highlight')).not.toBeInTheDocument())
    expect(dialog).toBeVisible()
    expect(screen.getByLabelText(/nome da disciplina/i)).toBeVisible()
    expect(onAction).not.toHaveBeenCalled()
  })

  it('turns a previous step into read-only review mode without changing the checkpoint', async () => {
    let state = applyTutorialTransition(INITIAL_TUTORIAL_STATE, { type: 'START', tutorialRunId: 'run-review' })
    state = applyTutorialTransition(state, { type: 'COMPLETE_STEP', actionId: 'continue' })
    const onAction = vi.fn()
    renderWithRouter(<TutorialWorkspace tutorial={makeTutorial(state, onAction)} onExit={vi.fn()} onSkipTutorial={vi.fn()} onContinueLater={vi.fn()} />)

    fireEvent.click(screen.getByTestId('tutorial-prev-button'))
    await waitFor(() => expect(screen.getByText(/a rever o passo 1/i)).toBeVisible())
    expect(document.querySelector('.tutorial-live-page')).toHaveClass('is-reviewing')
    expect(onAction).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /voltar ao passo atual/i }))
    expect(screen.queryByText(/a rever o passo 1/i)).not.toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /nova disciplina/i })).toBeEnabled()
  })

  it('advances explanatory steps from the guide panel', async () => {
    const state = applyTutorialTransition(INITIAL_TUTORIAL_STATE, { type: 'START', tutorialRunId: 'run-explanation' })
    const onAction = vi.fn()
    renderWithRouter(<TutorialWorkspace tutorial={makeTutorial(state, onAction)} onExit={vi.fn()} onSkipTutorial={vi.fn()} onContinueLater={vi.fn()} />)

    fireEvent.click(await screen.findByTestId('tutorial-complete-step'))
    expect(onAction).toHaveBeenCalledWith('continue')
  })

  it('renders the schedule preparation checkpoint after skipping setup exercises', async () => {
    let state = applyTutorialTransition(INITIAL_TUTORIAL_STATE, { type: 'START', tutorialRunId: 'run-schedule' })
    state = applyTutorialTransition(state, { type: 'COMPLETE_STEP', actionId: 'continue' })
    while (state.stepId !== 'schedule_prepare') state = applyTutorialTransition(state, { type: 'SKIP_STEP' })

    renderWithRouter(<TutorialWorkspace tutorial={makeTutorial(state)} onExit={vi.fn()} onSkipTutorial={vi.fn()} onContinueLater={vi.fn()} />)

    expect(await screen.findByRole('heading', { name: 'Horários Escolares' })).toBeVisible()
    expect(await screen.findByRole('button', { name: /gerar horário/i })).toBeEnabled()
  })

  it('renders the weekly close checkpoint reached after confirming a substitution', async () => {
    const state = {
      ...INITIAL_TUTORIAL_STATE,
      tutorialRunId: 'run-weekly-close',
      status: 'IN_PROGRESS',
      chapter: 2,
      stepId: 'debt_observe',
    }

    renderWithRouter(<TutorialWorkspace tutorial={makeTutorial(state)} onExit={vi.fn()} onSkipTutorial={vi.fn()} onContinueLater={vi.fn()} />)

    expect(await screen.findByRole('heading', { name: 'Fecho Semanal' })).toBeVisible()
    expect((await screen.findAllByText('Prof. António Silva')).length).toBeGreaterThan(0)
  })

  it.each(TUTORIAL_STEPS)('mounts checkpoint $stepNumber/$id with its real page fully loaded', async (step) => {
    const state = {
      ...INITIAL_TUTORIAL_STATE,
      tutorialRunId: `run-${step.id}`,
      status: 'IN_PROGRESS',
      chapter: step.chapter,
      stepId: step.id,
    }

    renderWithRouter(<TutorialWorkspace tutorial={makeTutorial(state)} onExit={vi.fn()} onSkipTutorial={vi.fn()} onContinueLater={vi.fn()} />)

    await expectCheckpointPageReady(step)
    expect(screen.getByTestId('tutorial-step-counter')).toHaveTextContent(`Passo ${TUTORIAL_STEPS.indexOf(step) + 1} de 24`)
  })
})
