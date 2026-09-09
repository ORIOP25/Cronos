import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'
import SignUpPage from '../pages/SignUpPage'
import { getLegalAcceptanceStorageKey } from '../features/legal/acceptanceStorage'

beforeEach(() => {
  sessionStorage.clear()
})

describe('SignUpPage legal copy', () => {
  it('renders the Cronos-branded legal acceptance message', () => {
    render(
      <MemoryRouter>
        <SignUpPage />
      </MemoryRouter>,
    )

    expect(screen.getByText(/Ao criar uma conta, concorda com os/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Termos de Serviço' })).toHaveAttribute('href', '/termos')
    expect(screen.getByRole('link', { name: 'Política de Privacidade' })).toHaveAttribute('href', '/privacidade')
  })

  it('renders one legal checkbox on the organization task and persists the choice', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/register/tasks/choose-organization']}>
        <SignUpPage />
      </MemoryRouter>,
    )

    const checkbox = screen.getByRole('checkbox', { name: /Li e concordo com os.*Termos de Serviço.*Política de Privacidade/i })
    expect(checkbox).not.toBeChecked()
    expect(screen.queryByText(/Ao criar uma conta, concorda com os/)).not.toBeInTheDocument()

    await user.click(checkbox)

    expect(checkbox).toBeChecked()
    expect(sessionStorage.getItem(getLegalAcceptanceStorageKey('user_test_123'))).toBe('true')
  })
})
