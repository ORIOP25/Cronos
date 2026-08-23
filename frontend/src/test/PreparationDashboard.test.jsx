import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { PreparationDashboard } from '../features/dashboard/PreparationDashboard'
import { getTutorialStorageKey } from '../features/tutorial/contracts'
import { INITIAL_SIMULATION_STATE, simulationReducer } from '../features/tutorial/simulationEngine'
import { saveTutorialState } from '../features/tutorial/tutorialStorage'
import { renderWithRouter } from './testUtils'

const bases = {
  depth: 0,
  percentage: 0,
  complete: false,
  steps: [],
}

describe('PreparationDashboard tutorial', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('opens the tutorial for a new preparation dashboard and advances its visible step', async () => {
    renderWithRouter(
      <PreparationDashboard
        orgId="org_test"
        userId="user_test"
        organizationName="Escola Teste"
        bases={bases}
      />,
      { initialEntries: ['/dashboard'] },
    )

    await waitFor(() => expect(screen.getByTestId('tutorial-modal')).toBeVisible())
    expect(screen.getByTestId('tutorial-step-counter')).toHaveTextContent('Passo 1 de 24')
    expect(screen.getByText('Estrutura da escola')).toBeVisible()

    fireEvent.click(screen.getByTestId('tutorial-next-button'))

    await waitFor(() => expect(screen.getByTestId('tutorial-step-counter')).toHaveTextContent('Passo 2 de 24'))
    expect(screen.getByText('Criar disciplina')).toBeVisible()
  })

  it('resumes a persisted run and advances from the resumed modal', async () => {
    let pausedState = simulationReducer(INITIAL_SIMULATION_STATE, {
      type: 'OPEN_TUTORIAL',
      payload: { tutorialRunId: 'run-paused' },
    })
    pausedState = simulationReducer(pausedState, { type: 'EXIT_TUTORIAL' })
    saveTutorialState(window.localStorage, getTutorialStorageKey('user_test', 'org_test'), pausedState)

    renderWithRouter(
      <PreparationDashboard
        orgId="org_test"
        userId="user_test"
        organizationName="Escola Teste"
        bases={bases}
      />,
      { initialEntries: ['/dashboard'] },
    )

    expect(screen.getByRole('button', { name: /retomar guia/i })).toBeVisible()
    expect(screen.queryByTestId('tutorial-modal')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /retomar guia/i }))
    await waitFor(() => expect(screen.getByTestId('tutorial-modal')).toBeVisible())

    fireEvent.click(screen.getByTestId('tutorial-next-button'))
    await waitFor(() => expect(screen.getByTestId('tutorial-step-counter')).toHaveTextContent('Passo 2 de 24'))
    expect(screen.getByText('Criar disciplina')).toBeVisible()
  })
})
