import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useLocation } from 'react-router-dom'

vi.mock('../features/readiness/data', () => ({
  usePrevalidation: vi.fn(),
}))

import { PreparationDashboard } from '../features/dashboard/PreparationDashboard'
import { getTutorialStorageKey } from '../features/tutorial/tutorialContent'
import { INITIAL_TUTORIAL_STATE, applyTutorialTransition } from '../features/tutorial/tutorialModel'
import { saveTutorialState } from '../features/tutorial/tutorialStorage'
import { renderWithRouter } from './testUtils'
import { usePrevalidation } from '../features/readiness/data'

const readinessCodes = [
  'ACTIVE_CLASSES',
  'MODULES',
  'CLASS_SUBJECTS',
  'TEACHER_ASSIGNMENT',
  'COMPATIBLE_ROOM',
  'TIMESLOTS',
  'TEACHER_AVAILABILITY',
]
const bases = {
  depth: 0,
  percentage: 0,
  complete: false,
  steps: readinessCodes.map((code) => ({ code, status: 'PENDING', route: '/config' })),
}
const completeBases = {
  depth: 7,
  percentage: 100,
  complete: true,
  fingerprint: 'fingerprint-v1',
  steps: readinessCodes.map((code) => ({ code, status: 'COMPLETE', route: '/config' })),
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location-probe">{location.pathname}{location.search}</output>
}

describe('PreparationDashboard tutorial entry points', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
    usePrevalidation.mockReturnValue({
      data: null,
      error: null,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
    })
  })

  it('keeps a new preparation dashboard on the dashboard until the guide CTA is selected', async () => {
    renderWithRouter(
      <><PreparationDashboard orgId="org_test" userId="user_test" organizationName="Escola Teste" bases={bases} /><LocationProbe /></>,
      { initialEntries: ['/dashboard'] },
    )
    await waitFor(() => expect(screen.getByTestId('location-probe')).toHaveTextContent('/dashboard'))
    expect(screen.getByRole('button', { name: /conhecer o guia/i })).toBeVisible()
  })

  it('offers resume without rendering a modal', async () => {
    let pausedState = applyTutorialTransition(INITIAL_TUTORIAL_STATE, { type: 'START', tutorialRunId: 'run-paused' })
    pausedState = applyTutorialTransition(pausedState, { type: 'ADVANCE', expectedStepId: 'curriculum' })
    saveTutorialState(window.localStorage, getTutorialStorageKey('user_test', 'org_test'), pausedState)

    renderWithRouter(
      <><PreparationDashboard orgId="org_test" userId="user_test" organizationName="Escola Teste" bases={bases} /><LocationProbe /></>,
      { initialEntries: ['/dashboard'] },
    )

    expect(await screen.findByRole('button', { name: /retomar guia/i })).toBeVisible()
    expect(screen.queryByTestId('tutorial-workspace')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /retomar guia/i }))
    await waitFor(() => expect(screen.getByTestId('location-probe')).toHaveTextContent('/guide?entry=resume'))
  })

  it('renders the seven-level validation chain and disables prevalidation below depth seven', () => {
    renderWithRouter(
      <PreparationDashboard
        orgId="org_test"
        userId="user_test"
        organizationName="Escola Teste"
        bases={bases}
        autoStartGuide={false}
      />,
    )

    expect(screen.getAllByTestId(/^preparation-level-/)).toHaveLength(7)
    expect(usePrevalidation).toHaveBeenCalledWith({ fingerprint: null, enabled: false })
    expect(screen.getByRole('button', { name: /gerar horário/i })).toBeDisabled()
  })

  it('renders modules before class-subject associations', () => {
    renderWithRouter(
      <PreparationDashboard bases={bases} autoStartGuide={false} />,
    )

    const levels = screen.getAllByTestId(/^preparation-level-/)
    expect(levels.map((level) => level.dataset.testid)).toEqual([
      'preparation-level-ACTIVE_CLASSES',
      'preparation-level-MODULES',
      'preparation-level-CLASS_SUBJECTS',
      'preparation-level-TEACHER_ASSIGNMENT',
      'preparation-level-COMPATIBLE_ROOM',
      'preparation-level-TIMESLOTS',
      'preparation-level-TEACHER_AVAILABILITY',
    ])
    expect(levels[1]).toHaveTextContent('2. Disciplinas com Módulos UFCD e carga horária definida')
    expect(levels[2]).toHaveTextContent('3. Associação Turma-Disciplina com ano curricular válido')
  })

  it('sends the teacher assignment action to the class subject page', () => {
    const teacherPendingBases = {
      ...bases,
      depth: 3,
      percentage: 42,
      steps: readinessCodes.map((code, index) => ({
        code,
        status: index < 3 ? 'COMPLETE' : 'PENDING',
        route: code === 'TEACHER_ASSIGNMENT' ? '/courses/7/classes/3/subjects' : '/config',
      })),
    }

    renderWithRouter(<PreparationDashboard bases={teacherPendingBases} autoStartGuide={false} />)

    const level = screen.getByTestId('preparation-level-TEACHER_ASSIGNMENT')
    expect(level).toHaveTextContent('4. Professor competente atribuído à disciplina da turma')
    expect(level.querySelector('a')).toHaveAttribute('href', '/courses/7/classes/3/subjects')
  })

  it('keeps preparation summary labels concise', () => {
    renderWithRouter(
      <PreparationDashboard
        orgId="org_test"
        userId="user_test"
        organizationName="Escola Teste"
        bases={{ ...bases, depth: 2, percentage: 28 }}
        autoStartGuide={false}
      />,
    )

    expect(screen.getByText('2/7')).toBeInTheDocument()
    expect(screen.queryByText(/nível de prontidão/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/níveis atingidos/i)).not.toBeInTheDocument()
    expect(screen.getByText('Escola Teste')).toBeInTheDocument()
    expect(screen.queryByText('Escola: Escola Teste')).not.toBeInTheDocument()
  })

  it('keeps the resume action free of decorative emoji', async () => {
    let pausedState = applyTutorialTransition(INITIAL_TUTORIAL_STATE, { type: 'START', tutorialRunId: 'run-paused' })
    pausedState = applyTutorialTransition(pausedState, { type: 'ADVANCE', expectedStepId: 'curriculum' })
    saveTutorialState(window.localStorage, getTutorialStorageKey('user_test', 'org_test'), pausedState)

    renderWithRouter(
      <PreparationDashboard orgId="org_test" userId="user_test" bases={bases} autoStartGuide={false} />,
    )

    const resumeButton = await screen.findByRole('button', { name: /retomar guia/i })
    expect(resumeButton).toHaveTextContent(/^Retomar guia$/)
  })

  it('sends the complete bases fingerprint and enables READY_WITH_WARNINGS generation', () => {
    usePrevalidation.mockReturnValue({
      data: { status: 'READY_WITH_WARNINGS', issues: [{ code: 'WARN', severity: 'WARNING', message: 'Aviso', route: '/schedules' }] },
      error: null,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
    })

    renderWithRouter(
      <PreparationDashboard
        orgId="org_test"
        userId="user_test"
        organizationName="Escola Teste"
        foundationStatus="COMPLETED"
        bases={completeBases}
        autoStartGuide={false}
      />,
    )

    expect(usePrevalidation).toHaveBeenCalledWith({ fingerprint: 'fingerprint-v1', enabled: true })
    expect(screen.getByRole('button', { name: /gerar horário/i })).toBeEnabled()
    expect(screen.getAllByText('Invariante satisfeito')).toHaveLength(7)
    expect(screen.queryByText(/issues de preparação/i)).not.toBeInTheDocument()
  })

  it('keeps generation disabled while prevalidation is checking', () => {
    usePrevalidation.mockReturnValue({
      data: null,
      error: null,
      isError: false,
      isFetching: true,
      refetch: vi.fn(),
    })

    renderWithRouter(<PreparationDashboard bases={completeBases} autoStartGuide={false} />)

    expect(screen.getByRole('button', { name: /a validar/i })).toBeDisabled()
    expect(screen.getByTestId('preparation-levels')).toBeVisible()
  })

})
