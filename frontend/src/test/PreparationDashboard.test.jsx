import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useLocation } from 'react-router-dom'

import { PreparationDashboard } from '../features/dashboard/PreparationDashboard'
import { getTutorialStorageKey } from '../features/tutorial/tutorialContent'
import { INITIAL_TUTORIAL_STATE, applyTutorialTransition } from '../features/tutorial/tutorialModel'
import { saveTutorialState } from '../features/tutorial/tutorialStorage'
import { renderWithRouter } from './testUtils'

const readinessCodes = [
  'ACTIVE_CLASSES',
  'MODULES',
  'TEACHERS',
  'TEACHER_ASSIGNMENT',
  'COMPATIBLE_ROOM',
  'TEACHER_AVAILABILITY',
]
const bases = {
  depth: 0,
  percentage: 0,
  complete: false,
  steps: readinessCodes.map((code) => ({ code, status: 'PENDING', route: '/config' })),
}
const completeBases = {
  depth: 6,
  percentage: 100,
  complete: true,
  fingerprint: 'fingerprint-v1',
  steps: readinessCodes.map((code) => ({ code, status: 'COMPLETE', route: '/config' })),
}

const missingReadinessIssues = [
  { code: 'MISSING_CALENDAR', message: 'Datas do ano letivo não configuradas.' },
  { code: 'MISSING_TIMESLOTS', message: 'Nenhum bloco de horário configurado.' },
  { code: 'MISSING_TEACHERS', message: 'Nenhum professor registado.' },
  { code: 'MISSING_CLASSES', message: 'Nenhuma turma ativa registada.' },
]

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location-probe">{location.pathname}{location.search}</output>
}

describe('PreparationDashboard tutorial entry points', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
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

  it('renders the six-level validation chain and disables generation below depth six', () => {
    renderWithRouter(
      <PreparationDashboard
        orgId="org_test"
        userId="user_test"
        organizationName="Escola Teste"
        bases={bases}
        autoStartGuide={false}
      />,
    )

    expect(screen.getAllByTestId(/^preparation-level-/)).toHaveLength(6)
    expect(screen.getByRole('button', { name: /gerar horário/i })).toBeDisabled()
  })

  it('renders teachers before teacher assignments', () => {
    renderWithRouter(
      <PreparationDashboard bases={bases} autoStartGuide={false} />,
    )

    const levels = screen.getAllByTestId(/^preparation-level-/)
    expect(levels.map((level) => level.dataset.testid)).toEqual([
      'preparation-level-ACTIVE_CLASSES',
      'preparation-level-MODULES',
      'preparation-level-TEACHERS',
      'preparation-level-TEACHER_ASSIGNMENT',
      'preparation-level-COMPATIBLE_ROOM',
      'preparation-level-TEACHER_AVAILABILITY',
    ])
    expect(levels[1]).toHaveTextContent('2. Disciplinas com módulos UFCD e carga horária definida')
    expect(levels[2]).toHaveTextContent('3. Pelo menos um professor ativo registado')
  })

  it('sends the teacher registration action to members without requiring competence', () => {
    const teacherPendingBases = {
      ...bases,
      depth: 2,
      percentage: 33,
      steps: readinessCodes.map((code, index) => ({
        code,
        status: index < 2 ? 'COMPLETE' : 'PENDING',
        route: code === 'TEACHERS' ? '/members' : '/config',
      })),
    }

    renderWithRouter(<PreparationDashboard bases={teacherPendingBases} autoStartGuide={false} />)

    const level = screen.getByTestId('preparation-level-TEACHERS')
    expect(level).toHaveTextContent('3. Pelo menos um professor ativo registado')
    expect(level).toHaveTextContent('A Realizar')
    expect(level.querySelector('a')).toHaveAttribute('href', '/members')
    expect(level).not.toHaveTextContent(/competên/i)
    expect(screen.queryByTestId('preparation-level-CLASS_SUBJECTS')).not.toBeInTheDocument()
    expect(screen.getByTestId('preparation-level-TEACHER_ASSIGNMENT')).toHaveTextContent('Bloqueado')
  })

  it('sends the teacher assignment action to the class subject page', () => {
    const teacherPendingBases = {
        ...bases,
        depth: 3,
      percentage: 50,
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
        bases={{ ...bases, depth: 2, percentage: 33 }}
        autoStartGuide={false}
      />,
    )

    expect(screen.getByText('2/6')).toBeInTheDocument()
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

  it('keeps READY_WITH_WARNINGS generation enabled without displaying validation issues', () => {
    renderWithRouter(
      <PreparationDashboard
        orgId="org_test"
        userId="user_test"
        organizationName="Escola Teste"
        foundationStatus="COMPLETED"
        bases={completeBases}
        prevalidation={{ status: 'READY_WITH_WARNINGS', issues: [{ code: 'WARN', severity: 'WARNING', message: 'Aviso', route: '/schedules' }] }}
        autoStartGuide={false}
      />,
    )

    expect(screen.getByRole('button', { name: /gerar horário/i })).toBeEnabled()
    expect(screen.getAllByText('Concluído')).toHaveLength(6)
    expect(screen.queryByText(/issues de preparação/i)).not.toBeInTheDocument()
    expect(screen.queryByText('Aviso')).not.toBeInTheDocument()
  })

  it.each([
    ['bases incompletas', bases],
    ['bases completas', completeBases],
  ])('does not display missing-resource issues for %s', (_, basesState) => {
    renderWithRouter(
      <PreparationDashboard
        bases={basesState}
        prevalidation={{
          status: 'BLOCKED',
          issues: missingReadinessIssues.map((issue) => ({
            ...issue,
            severity: 'BLOCKER',
            route: '/config',
          })),
        }}
        autoStartGuide={false}
      />,
    )

    expect(screen.queryByTestId('preparation-issues')).not.toBeInTheDocument()
    for (const issue of missingReadinessIssues) {
      expect(screen.queryByText(issue.code)).not.toBeInTheDocument()
      expect(screen.queryByText(issue.message)).not.toBeInTheDocument()
    }
  })

  it('keeps generation disabled when prevalidation is blocked and links to schedules for review', () => {
    renderWithRouter(
      <PreparationDashboard
        bases={completeBases}
        prevalidation={{
          status: 'BLOCKED',
          issues: [{
            code: 'MISSING_TEACHERS',
            severity: 'BLOCKER',
            message: 'Nenhum professor registado.',
            route: '/members',
          }],
        }}
        autoStartGuide={false}
      />,
    )

    expect(screen.getByRole('button', { name: /gerar horário/i })).toBeDisabled()
    expect(screen.getByRole('link', { name: /horários/i })).toHaveAttribute('href', '/schedules')
    expect(screen.queryByText('MISSING_TEACHERS')).not.toBeInTheDocument()
    expect(screen.queryByText('Nenhum professor registado.')).not.toBeInTheDocument()
    expect(screen.queryByText(/identificados abaixo/i)).not.toBeInTheDocument()
  })

  it('does not display readiness success when bases are incomplete even if prevalidation is not blocked', () => {
    renderWithRouter(
      <PreparationDashboard
        bases={{ ...bases, percentage: 50, depth: 3, complete: false }}
        prevalidation={{ status: 'READY', issues: [] }}
        autoStartGuide={false}
      />,
    )

    expect(screen.getByRole('button', { name: /gerar horário/i })).toBeDisabled()
    expect(screen.queryByText(/pronta para gerar o horário/i)).not.toBeInTheDocument()
    expect(screen.getByText(/Preparação da escola: 50%/i)).toBeInTheDocument()
  })

})
