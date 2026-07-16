import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useSignIn } from '@clerk/react'
import BrandPanel from '../components/auth/BrandPanel'
import { BRAND_STATS_LOGIN, BRAND_TAGLINE_LOGIN } from '../utils/authDesign'

const EMAIL_QUOTA_ERROR = 'dev_monthly_email_limit_exceeded'

function errorCode(error) {
  return error?.code || error?.errors?.[0]?.code
}

function passwordRecoveryErrorMessage(error) {
  if (errorCode(error) === EMAIL_QUOTA_ERROR) {
    return 'A instância de desenvolvimento atingiu o limite mensal de emails. Entre com Google ou contacte o administrador; insistir no reenvio não fará chegar um email.'
  }

  const clerkError = error?.errors?.[0] || error
  return clerkError?.longMessage
    || clerkError?.message
    || 'Não foi possível concluir a recuperação. Tente novamente.'
}

function RecoveryAlternatives() {
  return (
    <div className="zen-auth-recovery-alternatives">
      <p>Precisa de entrar já e usa Gmail?</p>
      <Link to="/login">Entrar com Google no ecrã de acesso</Link>
    </div>
  )
}

export default function ForgotPasswordPage() {
  const { signIn, errors, fetchStatus } = useSignIn()
  const navigate = useNavigate()
  const [step, setStep] = useState('email')
  const [emailAddress, setEmailAddress] = useState('')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [localError, setLocalError] = useState('')

  const isFetching = fetchStatus === 'fetching'

  async function execute(action) {
    setLocalError('')
    try {
      const result = await action()
      if (result?.error) {
        setLocalError(passwordRecoveryErrorMessage(result.error))
        return false
      }
      return true
    } catch (error) {
      setLocalError(passwordRecoveryErrorMessage(error))
      return false
    }
  }

  async function sendCode(event) {
    event.preventDefault()
    if (!signIn) return

    const created = await execute(() => signIn.create({ identifier: emailAddress.trim() }))
    if (!created) return

    const sent = await execute(() => signIn.resetPasswordEmailCode.sendCode())
    if (sent) setStep('code')
  }

  async function verifyCode(event) {
    event.preventDefault()
    if (!signIn) return

    const verified = await execute(() => signIn.resetPasswordEmailCode.verifyCode({ code: code.trim() }))
    if (verified) setStep('password')
  }

  async function submitPassword(event) {
    event.preventDefault()
    if (!signIn) return
    if (password !== confirmPassword) {
      setLocalError('As palavras-passe não coincidem.')
      return
    }

    const submitted = await execute(() => signIn.resetPasswordEmailCode.submitPassword({
      password,
      signOutOfOtherSessions: true,
    }))
    if (!submitted) return

    await execute(() => signIn.finalize({
      navigate: async ({ session, decorateUrl }) => {
        const destination = decorateUrl(session?.currentTask ? '/onboarding' : '/')
        if (destination.startsWith('http')) {
          window.location.href = destination
          return
        }
        navigate(destination)
      },
    }))
  }

  const fieldError = errors?.fields?.identifier?.message || errors?.fields?.code?.message
  const visibleError = localError || fieldError

  return (
    <div className="zen-auth-page">
      <div className="zen-auth-layout">
        <BrandPanel tagline={BRAND_TAGLINE_LOGIN} stats={BRAND_STATS_LOGIN} />

        <div className="zen-auth-form-side">
          <div className="zen-auth-form-wrapper">
            <section className="zen-auth-recovery-card" aria-labelledby="recovery-title">
              {step === 'email' && (
                <>
                  <h1 id="recovery-title">Recuperar palavra-passe</h1>
                  <p>
                    Introduza o email da conta. Enviaremos um código para confirmar a sua
                    identidade e escolher uma nova palavra-passe.
                  </p>
                  <form onSubmit={sendCode}>
                    <label htmlFor="recovery-email">Email</label>
                    <input
                      id="recovery-email"
                      type="email"
                      autoComplete="email"
                      required
                      value={emailAddress}
                      onChange={(event) => setEmailAddress(event.target.value)}
                    />
                    <button type="submit" disabled={!signIn || isFetching}>
                      {isFetching ? 'A enviar…' : 'Enviar código'}
                    </button>
                  </form>
                </>
              )}

              {step === 'code' && (
                <>
                  <h1 id="recovery-title">Introduza o código</h1>
                  <p>
                    O serviço de autenticação aceitou o pedido. Procure o código de
                    verificação enviado para {emailAddress}, incluindo no spam.
                  </p>
                  <form onSubmit={verifyCode}>
                    <label htmlFor="recovery-code">Código de verificação</label>
                    <input
                      id="recovery-code"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      required
                      value={code}
                      onChange={(event) => setCode(event.target.value)}
                    />
                    <button type="submit" disabled={isFetching}>
                      {isFetching ? 'A verificar…' : 'Verificar código'}
                    </button>
                  </form>
                </>
              )}

              {step === 'password' && (
                <>
                  <h1 id="recovery-title">Escolha uma nova palavra-passe</h1>
                  <form onSubmit={submitPassword}>
                    <label htmlFor="recovery-password">Nova palavra-passe</label>
                    <input
                      id="recovery-password"
                      type="password"
                      autoComplete="new-password"
                      required
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                    />
                    <label htmlFor="recovery-confirm-password">Confirmar palavra-passe</label>
                    <input
                      id="recovery-confirm-password"
                      type="password"
                      autoComplete="new-password"
                      required
                      value={confirmPassword}
                      onChange={(event) => setConfirmPassword(event.target.value)}
                    />
                    <button type="submit" disabled={isFetching}>
                      {isFetching ? 'A guardar…' : 'Guardar e entrar'}
                    </button>
                  </form>
                </>
              )}

              {visibleError && <div className="zen-auth-recovery-error" role="alert">{visibleError}</div>}
              <RecoveryAlternatives />
              <Link to="/login" className="zen-auth-back-link">Voltar ao início de sessão</Link>
            </section>
          </div>
        </div>
      </div>
    </div>
  )
}
