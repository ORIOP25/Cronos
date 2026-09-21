import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { renderWithRouter } from './testUtils'
import { resetClerkState, setClerkSignInState } from './setup'
import SignInPage from '../pages/SignInPage'
import ForgotPasswordPage from '../pages/ForgotPasswordPage'
import { CLERK_APPEARANCE_AUTH } from '../utils/authDesign'

describe('password recovery', () => {
  beforeEach(() => {
    resetClerkState()
  })

  it('makes the existing-account path explicit on the sign-in page', () => {
    renderWithRouter(<SignInPage />)

    expect(screen.getByTestId('clerk-sign-in')).toHaveAttribute('data-fallback-redirect-url', '/')
    expect(screen.getByRole('link', { name: /recuperar palavra-passe/i })).toHaveAttribute(
      'href',
      '/recuperar-palavra-passe',
    )
    expect(screen.getByText(/entrar com google/i)).toBeInTheDocument()
  })

  it('renders the organization task on its dedicated route', () => {
    renderWithRouter(<SignInPage />, { initialEntries: ['/login/tasks/choose-organization'] })

    const task = screen.getByTestId('clerk-task-choose-organization')
    expect(task).toHaveAttribute('data-redirect-url-complete', '/foundation')
    expect(task).toHaveAttribute('data-appearance', JSON.stringify(CLERK_APPEARANCE_AUTH))
    expect(screen.queryByTestId('clerk-sign-in')).not.toBeInTheDocument()
    expect(screen.queryByText(/recuperar palavra-passe/i)).not.toBeInTheDocument()
  })

  it('requests a reset code through the supported Clerk strategy', async () => {
    const create = vi.fn().mockResolvedValue({ error: null })
    const sendCode = vi.fn().mockResolvedValue({ error: null })
    setClerkSignInState({
      signIn: {
        create,
        resetPasswordEmailCode: { sendCode },
      },
    })
    renderWithRouter(<ForgotPasswordPage />)

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'tei.xeira.mariana512@gmail.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /enviar código/i }))

    await waitFor(() => {
      expect(create).toHaveBeenCalledWith({
        identifier: 'tei.xeira.mariana512@gmail.com',
      })
      expect(sendCode).toHaveBeenCalledOnce()
    })
    expect(screen.getByRole('heading', { name: /introduza o código/i })).toBeInTheDocument()
  })

  it('explains the development email quota instead of showing a generic error', async () => {
    const create = vi.fn().mockResolvedValue({ error: null })
    const sendCode = vi.fn().mockResolvedValue({
      error: { code: 'dev_monthly_email_limit_exceeded' },
    })
    setClerkSignInState({
      signIn: {
        create,
        resetPasswordEmailCode: { sendCode },
      },
    })
    renderWithRouter(<ForgotPasswordPage />)

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'tei.xeira.mariana512@gmail.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /enviar código/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/limite mensal de emails/i)
    expect(screen.getByText(/entrar com google/i)).toBeInTheDocument()
  })

  it('verifies the code, changes the password and finalizes the session', async () => {
    const create = vi.fn().mockResolvedValue({ error: null })
    const sendCode = vi.fn().mockResolvedValue({ error: null })
    const verifyCode = vi.fn().mockResolvedValue({ error: null })
    const submitPassword = vi.fn().mockResolvedValue({ error: null })
    const finalize = vi.fn().mockResolvedValue({ error: null })
    setClerkSignInState({
      signIn: {
        create,
        resetPasswordEmailCode: { sendCode, verifyCode, submitPassword },
        finalize,
      },
    })
    renderWithRouter(<ForgotPasswordPage />)

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'tei.xeira.mariana512@gmail.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /enviar código/i }))
    await screen.findByRole('heading', { name: /introduza o código/i })

    fireEvent.change(screen.getByLabelText(/código de verificação/i), {
      target: { value: '123456' },
    })
    fireEvent.click(screen.getByRole('button', { name: /verificar código/i }))
    await screen.findByRole('heading', { name: /nova palavra-passe/i })

    fireEvent.change(screen.getByLabelText(/^nova palavra-passe$/i), {
      target: { value: 'Uma-palavra-passe-segura-123!' },
    })
    fireEvent.change(screen.getByLabelText(/confirmar palavra-passe/i), {
      target: { value: 'Uma-palavra-passe-segura-123!' },
    })
    fireEvent.click(screen.getByRole('button', { name: /guardar e entrar/i }))

    await waitFor(() => {
      expect(verifyCode).toHaveBeenCalledWith({ code: '123456' })
      expect(submitPassword).toHaveBeenCalledWith({
        password: 'Uma-palavra-passe-segura-123!',
        signOutOfOtherSessions: true,
      })
      expect(finalize).toHaveBeenCalledOnce()
    })
  })
})
