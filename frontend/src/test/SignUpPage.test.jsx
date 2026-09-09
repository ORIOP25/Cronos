import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import SignUpPage from '../pages/SignUpPage'

describe('SignUpPage legal copy', () => {
  it('renders information and links without collecting legal acceptance', () => {
    render(
      <MemoryRouter>
        <SignUpPage />
      </MemoryRouter>,
    )

    expect(screen.getByText(/Ao criar uma conta, concorda com os/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Termos de Serviço' })).toHaveAttribute('href', '/termos')
    expect(screen.getByRole('link', { name: 'Acordo de Tratamento de Dados' })).toHaveAttribute('href', '/dpa')
    expect(screen.getByRole('link', { name: 'Política de Privacidade' })).toHaveAttribute('href', '/privacidade')
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })
})
