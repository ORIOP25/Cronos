import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import SignUpPage from '../pages/SignUpPage'
import { CLERK_LEGAL_UNSAFE_METADATA } from '../features/legal/data'

describe('SignUpPage legal copy', () => {
  it('passes legal versions to Clerk and keeps the document links nearby', () => {
    render(
      <MemoryRouter>
        <SignUpPage />
      </MemoryRouter>,
    )

    const signUp = screen.getByTestId('clerk-sign-up')
    expect(signUp).toHaveAttribute('data-fallback-redirect-url', '/foundation')
    expect(JSON.parse(signUp.getAttribute('data-unsafe-metadata'))).toEqual(CLERK_LEGAL_UNSAFE_METADATA)
    expect(screen.getByText(/Ao criar uma conta e uma escola, confirma que tem poderes para a vincular/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Termos de Serviço' })).toHaveAttribute('href', '/termos')
    expect(screen.getByRole('link', { name: 'Acordo de Tratamento de Dados' })).toHaveAttribute('href', '/dpa')
    expect(screen.getByRole('link', { name: 'Política de Privacidade' })).toHaveAttribute('href', '/privacidade')
  })
})
