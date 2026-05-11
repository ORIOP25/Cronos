import React, { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import apiClient from '../apiClient'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '../store'
import { getDefaultRouteForRole } from '../roleAccess'
import { TXT } from '../utils/terminology'
import BrandPanel from '../components/auth/BrandPanel'

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
              A
            </span>
            <span className="zen-caps" style={{ color: 'var(--brand-600)', fontSize: '0.65rem' }}>
              Aperius
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
      <BrandPanel
        tagline="Gestão de horários escolares com clareza, controlo e sem stress. Pensado para o Ensino Profissional em Portugal."
        stats={[
          { value: '<1min', label: 'Gerar horário' },
          { value: '100%', label: 'Automático' },
          { value: 'PT-PT', label: 'Ensino Profissional' },
        ]}
      />
    </div>
  )
}

export default Login
