import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

  it('shows an explicit entry screen before opening the live tutorial', async () => {
    const user = userEvent.setup()
    renderWithRouter(<Guide />, { initialEntries: ['/guide'] })

    await waitFor(() => expect(screen.getByRole('button', { name: /conhecer o guia/i })).toBeInTheDocument())
    expect(screen.queryByTestId('tutorial-workspace')).not.toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Cronos' })).toHaveAttribute('src', '/logo.png')
    expect(screen.queryByText('C')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /conhecer o guia/i }))
    await waitFor(() => expect(screen.getByTestId('tutorial-workspace')).toBeInTheDocument())
    expect(screen.getByTestId('tutorial-step-counter')).toHaveTextContent('Passo 1 de 13')
  })

  it('opens the requested path directly from an explicit dashboard entry', async () => {
    renderWithRouter(<Guide />, { initialEntries: ['/guide?entry=start'] })

    expect(await screen.findByTestId('tutorial-workspace')).toBeInTheDocument()
    expect(screen.getByTestId('tutorial-step-counter')).toHaveTextContent('Passo 1 de 13')
  })
})
