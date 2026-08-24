import { screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../features/tutorial/tutorialTelemetry', () => ({
  sendTutorialTelemetryEvent: vi.fn().mockResolvedValue(undefined),
}))

import Guide from '../pages/Guide'
import { renderWithRouter } from './testUtils'

describe('Guide', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('opens the live tutorial after storage hydration', async () => {
    renderWithRouter(<Guide />, { initialEntries: ['/guide'] })

    await waitFor(() => expect(screen.getByTestId('tutorial-workspace')).toBeInTheDocument())
    expect(screen.getByTestId('tutorial-step-counter')).toHaveTextContent('Passo 1 de 24')
  })
})
