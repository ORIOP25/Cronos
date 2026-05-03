import React, { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import apiClient from '../apiClient'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '../store'
import { getDefaultRouteForRole } from '../roleAccess'
import { TXT } from '../utils/terminology'

import {
  CButton, CCol, CContainer, CForm, CFormInput,
  CInputGroup, CInputGroupText, CRow, CAlert, CSpinner,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilLockLocked, cilEnvelopeClosed } from '@coreui/icons'

const Login = () => {
  const navigate = useNavigate()
  const setLogin = useAuthStore((state) => state.login)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errorMsg, setErrorMsg] = useState('')

  const mutation = useMutation({
    mutationFn: async (credentials) => {
      const formData = new URLSearchParams()
      formData.append('username', credentials.email)
      formData.append('password', credentials.password)
      const res = await apiClient.post('/auth/token', formData, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      })
      return res.data
    },
    onSuccess: (data) => {
      setLogin(data)
      navigate(getDefaultRouteForRole(data.role))
    },
    onError: () => {
      setErrorMsg('Credenciais inválidas. Verifique o email e a password e tente novamente.')
    }
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    setErrorMsg('')
    mutation.mutate({ email, password })
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh', backgroundColor: 'var(--brand-50)' }}>
      {/* ── FORM SIDE ── */}
      <div style={{
        flex: '1 1 60%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '48px 32px',
      }}>
        <div className="zen-reveal" style={{ width: '100%', maxWidth: '420px' }}>
          {/* Brand mark */}
          <Link to="/" style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '10px',
            textDecoration: 'none',
            marginBottom: '48px',
          }}>
            <span style={{
              width: '36px',
              height: '36px',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: 'var(--brand-800)',
              color: 'var(--brand-50)',
              fontFamily: 'var(--font-display)',
              fontSize: '0.75rem',
              fontWeight: 700,
              letterSpacing: '0.08em',
            }}>
              HZ
            </span>
            <span className="zen-caps" style={{ color: 'var(--brand-600)', fontSize: '0.65rem' }}>
              Horário Zen
            </span>
          </Link>

          <h1 className="text-display" style={{
            fontSize: 'clamp(1.8rem, 3vw, 2.4rem)',
            color: 'var(--brand-950)',
            marginBottom: '8px',
          }}>
            Bem-vindo de volta
          </h1>
          <p style={{
            color: 'var(--brand-600)',
            fontSize: '0.95rem',
            marginBottom: '36px',
            lineHeight: 1.6,
          }}>
            Entre na sua conta para aceder ao painel de gestão de horários da sua escola.
          </p>

          {errorMsg && (
            <CAlert color="danger" className="mb-4 py-2 small">
              {errorMsg}
            </CAlert>
          )}

          <CForm onSubmit={handleSubmit}>
            <div className="mb-3">
              <label htmlFor="loginEmail" className="form-label" style={{
                fontSize: '0.8rem',
                fontWeight: 600,
                color: 'var(--brand-800)',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                marginBottom: '6px',
              }}>
                Email
              </label>
              <CInputGroup>
                <CInputGroupText style={{
                  backgroundColor: 'var(--brand-50)',
                  border: '1px solid var(--color-border-default)',
                  borderRight: 'none',
                }}>
                  <CIcon icon={cilEnvelopeClosed} size="sm" />
                </CInputGroupText>
                <CFormInput
                  id="loginEmail"
                  type="email"
                  placeholder="o seu email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  style={{
                    border: '1px solid var(--color-border-default)',
                    borderLeft: 'none',
                    fontSize: '0.92rem',
                    padding: '10px 12px',
                  }}
                />
              </CInputGroup>
            </div>

            <div className="mb-4">
              <label htmlFor="loginPassword" className="form-label" style={{
                fontSize: '0.8rem',
                fontWeight: 600,
                color: 'var(--brand-800)',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                marginBottom: '6px',
              }}>
                Password
              </label>
              <CInputGroup>
                <CInputGroupText style={{
                  backgroundColor: 'var(--brand-50)',
                  border: '1px solid var(--color-border-default)',
                  borderRight: 'none',
                }}>
                  <CIcon icon={cilLockLocked} size="sm" />
                </CInputGroupText>
                <CFormInput
                  id="loginPassword"
                  type="password"
                  placeholder="a sua password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  style={{
                    border: '1px solid var(--color-border-default)',
                    borderLeft: 'none',
                    fontSize: '0.92rem',
                    padding: '10px 12px',
                  }}
                />
              </CInputGroup>
            </div>

            <CButton
              type="submit"
              className="btn-zen btn-zen-primary w-100 mb-4"
              disabled={mutation.isPending}
              style={{ padding: '12px' }}
            >
              {mutation.isPending ? (
                <><CSpinner size="sm" className="me-2" />A entrar…</>
              ) : (
                'Entrar'
              )}
            </CButton>

            <div style={{ textAlign: 'center' }}>
              <span style={{ color: 'var(--brand-600)', fontSize: '0.88rem' }}>
                Ainda não tem conta?{' '}
              </span>
              <Link to="/register" className="zen-link-underline" style={{
                color: 'var(--brand-800)',
                fontWeight: 600,
                textDecoration: 'none',
                fontSize: '0.88rem',
              }}>
                Criar conta
              </Link>
            </div>
          </CForm>
        </div>
      </div>

      {/* ── BRAND PANEL ── */}
      <div className="zen-login-brand-panel" style={{
        flex: '1 1 40%',
        position: 'relative',
        backgroundColor: 'var(--brand-950)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '64px 40px',
        overflow: 'hidden',
        minHeight: '100vh',
      }}>
        {/* Grain texture */}
        <div className="luxury-noise" style={{ opacity: 0.03, zIndex: 1 }} />

        {/* Decorative elements */}
        <div style={{
          position: 'absolute',
          top: '15%',
          right: '15%',
          width: '180px',
          height: '180px',
          border: '1px solid rgba(214, 176, 112, 0.12)',
          transform: 'rotate(15deg)',
          zIndex: 1,
        }} />
        <div style={{
          position: 'absolute',
          bottom: '20%',
          left: '10%',
          width: '120px',
          height: '120px',
          border: '1px solid rgba(214, 176, 112, 0.08)',
          transform: 'rotate(-10deg)',
          zIndex: 1,
        }} />
        <div style={{
          position: 'absolute',
          top: '30%',
          left: '20%',
          width: '1px',
          height: '80px',
          background: 'var(--brand-500)',
          opacity: 0.2,
          zIndex: 1,
        }} />

        {/* Content */}
        <div style={{ position: 'relative', zIndex: 2, textAlign: 'center' }}>
          <div style={{
            width: '80px',
            height: '80px',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            border: '2px solid var(--brand-500)',
            borderRadius: '50%',
            marginBottom: '28px',
          }}>
            <span style={{
              fontFamily: 'var(--font-display)',
              fontSize: '1.4rem',
              fontWeight: 700,
              color: 'var(--brand-500)',
              letterSpacing: '0.06em',
            }}>
              HZ
            </span>
          </div>

          <h2 className="text-display" style={{
            color: 'var(--brand-50)',
            fontSize: 'clamp(2rem, 4vw, 3rem)',
            marginBottom: '12px',
            letterSpacing: '-0.02em',
          }}>
            Horário{' '}
            <span style={{ color: 'var(--brand-500)' }}>Zen</span>
          </h2>

          <div style={{
            width: '40px',
            height: '1px',
            background: 'var(--brand-500)',
            margin: '16px auto 20px',
            opacity: 0.6,
          }} />

          <p style={{
            color: 'rgba(251, 244, 231, 0.5)',
            fontSize: '0.9rem',
            lineHeight: 1.7,
            maxWidth: '280px',
            margin: '0 auto 40px',
          }}>
            Gestão de horários escolares com clareza, controlo e sem stress.
            Pensado para o Ensino Profissional em Portugal.
          </p>

          <div style={{
            display: 'flex',
            gap: '24px',
            justifyContent: 'center',
          }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{
                fontFamily: 'var(--font-display)',
                fontSize: '1.5rem',
                color: 'var(--brand-500)',
                fontWeight: 700,
              }}>
                &lt;1min
              </div>
              <div style={{
                fontSize: '0.65rem',
                color: 'rgba(251, 244, 231, 0.35)',
                textTransform: 'uppercase',
                letterSpacing: '0.1em',
                marginTop: '4px',
              }}>
                Gerar horário
              </div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{
                fontFamily: 'var(--font-display)',
                fontSize: '1.5rem',
                color: 'var(--brand-500)',
                fontWeight: 700,
              }}>
                100%
              </div>
              <div style={{
                fontSize: '0.65rem',
                color: 'rgba(251, 244, 231, 0.35)',
                textTransform: 'uppercase',
                letterSpacing: '0.1em',
                marginTop: '4px',
              }}>
                Automático
              </div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{
                fontFamily: 'var(--font-display)',
                fontSize: '1.5rem',
                color: 'var(--brand-500)',
                fontWeight: 700,
              }}>
                PT-PT
              </div>
              <div style={{
                fontSize: '0.65rem',
                color: 'rgba(251, 244, 231, 0.35)',
                textTransform: 'uppercase',
                letterSpacing: '0.1em',
                marginTop: '4px',
              }}>
                Ensino Profissional
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Login
