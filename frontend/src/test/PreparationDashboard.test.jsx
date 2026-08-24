import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useLocation } from 'react-router-dom'

vi.mock('../features/readiness/data', () => ({
  usePrevalidation: vi.fn(),
}))

import { PreparationDashboard } from '../features/dashboard/PreparationDashboard'
import { getTutorialStorageKey } from '../features/tutorial/tutorialScenario'
import { INITIAL_TUTORIAL_STATE, applyTutorialTransition } from '../features/tutorial/tutorialModel'
import { saveTutorialState } from '../features/tutorial/tutorialStorage'
import { renderWithRouter } from './testUtils'
import { usePrevalidation } from '../features/readiness/data'

const bases = { depth: 0, percentage: 0, complete: false, steps: [] }
const completeBases = {
  depth: 7,
  percentage: 100,
  complete: true,
  fingerprint: 'fingerprint-v1',
  steps: [
    'ACTIVE_CLASSES',
    'CLASS_SUBJECTS',
    'MODULES',
    'TEACHER_ASSIGNMENT',
    'COMPATIBLE_ROOM',
    'TIMESLOTS',
    'TEACHER_AVAILABILITY',
  ].map((code) => ({ code, status: 'COMPLETE', route: '/config' })),
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location-probe">{location.pathname}</output>
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

  it('redirects a new preparation dashboard to the workspace route', async () => {
    renderWithRouter(
      <><PreparationDashboard orgId="org_test" userId="user_test" organizationName="Escola Teste" bases={bases} /><LocationProbe /></>,
      { initialEntries: ['/dashboard'] },
    )
    await waitFor(() => expect(screen.getByTestId('location-probe')).toHaveTextContent('/guide'))
  })

  it('offers resume without rendering a modal', async () => {
    let pausedState = applyTutorialTransition(INITIAL_TUTORIAL_STATE, { type: 'START', tutorialRunId: 'run-paused' })
    pausedState = applyTutorialTransition(pausedState, { type: 'COMPLETE_STEP', actionId: 'continue' })
    saveTutorialState(window.localStorage, getTutorialStorageKey('user_test', 'org_test'), pausedState)

    renderWithRouter(
      <><PreparationDashboard orgId="org_test" userId="user_test" organizationName="Escola Teste" bases={bases} /><LocationProbe /></>,
      { initialEntries: ['/dashboard'] },
    )

    expect(await screen.findByRole('button', { name: /retomar guia/i })).toBeVisible()
    expect(screen.queryByTestId('tutorial-workspace')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /retomar guia/i }))
    await waitFor(() => expect(screen.getByTestId('location-probe')).toHaveTextContent('/guide'))
  })

  it('renders exactly five preparation blocks and disables prevalidation below depth seven', () => {
    renderWithRouter(
      <PreparationDashboard
        orgId="org_test"
        userId="user_test"
        organizationName="Escola Teste"
        bases={bases}
        autoStartGuide={false}
      />,
    )

    expect(screen.getAllByTestId(/^preparation-block-/)).toHaveLength(5)
    expect(usePrevalidation).toHaveBeenCalledWith({ fingerprint: null, enabled: false })
    expect(screen.getByRole('button', { name: /gerar primeiro horário/i })).toBeDisabled()
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
    expect(screen.getByRole('button', { name: /gerar primeiro horário/i })).toBeEnabled()
    expect(screen.getByTestId('preparation-block-first-schedule')).toHaveTextContent('Concluído.')
    expect(screen.getByTestId('preparation-issues')).toHaveTextContent('WARN')
  })

  it('keeps a BLOCKED complete chain actionable through the blocker route', async () => {
    usePrevalidation.mockReturnValue({
      data: { status: 'BLOCKED', issues: [{ code: 'ROOM_REQUIRED', severity: 'BLOCKER', message: 'Configure uma sala.', route: '/rooms' }] },
      error: null,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
    })

    renderWithRouter(
      <><PreparationDashboard bases={completeBases} autoStartGuide={false} /><LocationProbe /></>,
      { initialEntries: ['/dashboard'] },
    )

    const correctionButton = within(screen.getByTestId('preparation-block-first-schedule')).getByRole(
      'button',
      { name: /corrigir bloco/i },
    )
    expect(correctionButton).toBeVisible()
    expect(screen.getByTestId('preparation-block-first-schedule')).not.toHaveTextContent('Concluído.')
    fireEvent.click(correctionButton)
    await waitFor(() => expect(screen.getByTestId('location-probe')).toHaveTextContent('/rooms'))
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
    expect(screen.getByTestId('preparation-block-first-schedule')).toHaveTextContent('Prevalidation: CHECKING.')
  })

  it.each([
    {
      name: 'network failure',
      error: new Error('network error'),
      message: /não foi possível ligar ao servidor/i,
    },
    {
      name: 'stale fingerprint',
      error: { response: { status: 409, data: { detail: { code: 'PREFLIGHT_STALE' } } } },
      message: /dados da escola foram alterados/i,
    },
  ])('exposes an actionable retry for prevalidation $name', async ({ error, message }) => {
    const refetch = vi.fn()
    usePrevalidation.mockReturnValue({
      data: null,
      error,
      isError: true,
      isFetching: false,
      refetch,
    })

    renderWithRouter(<PreparationDashboard bases={completeBases} autoStartGuide={false} />)

    expect(screen.getByRole('alert')).toHaveTextContent(message)
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }))
    expect(refetch).toHaveBeenCalledOnce()
  })
})
