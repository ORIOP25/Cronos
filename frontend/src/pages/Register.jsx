import React, { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import apiClient from '../apiClient'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '../store'
import { TXT } from '../utils/terminology'
import BrandPanel from '../components/auth/BrandPanel'

import {
  CButton, CCol, CContainer, CForm, CFormInput,
  CInputGroup, CInputGroupText, CRow, CAlert, CSpinner,
  CFormFeedback,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import {
  cilLockLocked, cilUser, cilInstitution, cilEnvelopeClosed, cilCheckCircle,
} from '@coreui/icons'

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

const MIN_PASSWORD_LENGTH = 6

function validateField(name, value, form) {
  switch (name) {
    case 'schoolName':
      if (!value || value.trim().length < 2) return 'O nome da escola deve ter pelo menos 2 caracteres.'
      return ''
    case 'adminName':
      if (!value || value.trim().length < 2) return 'O nome do administrador deve ter pelo menos 2 caracteres.'
      return ''
    case 'email':
      if (!value || !EMAIL_REGEX.test(value)) return 'Introduza um email válido.'
      return ''
    case 'password':
      if (!value || value.length < MIN_PASSWORD_LENGTH) return `A password deve ter pelo menos ${MIN_PASSWORD_LENGTH} caracteres.`
      return ''
    case 'confirmPassword':
      if (value !== form.password) return 'As passwords não coincidem.'
      return ''
    default:
      return ''
  }
}

function validateForm(form) {
  const errors = {}
  for (const key of ['schoolName', 'adminName', 'email', 'password', 'confirmPassword']) {
    const msg = validateField(key, form[key], form)
    if (msg) errors[key] = msg
  }
  return errors
}

const Register = () => {
  const navigate = useNavigate()
  const setLogin = useAuthStore((state) => state.login)

  const [form, setForm] = useState({
    schoolName: '',
    adminName: '',
    email: '',
    password: '',
    confirmPassword: '',
  })
  const [fieldErrors, setFieldErrors] = useState({})
  const [serverError, setServerError] = useState('')

  const mutation = useMutation({
    mutationFn: async (data) => {
      const res = await apiClient.post('/auth/register', {
        school_name: data.schoolName,
        admin_name: data.adminName,
        email: data.email,
        password: data.password,
      })
      return res.data
    },
    onSuccess: (data) => {
      setLogin(data)
      navigate('/dashboard')
    },
    onError: (err) => {
      const detail = err?.response?.data?.detail
      if (typeof detail === 'string' && detail.trim()) {
        setServerError(detail)
      } else if (Array.isArray(detail)) {
        setServerError(detail.map((e) => e.msg || e.message || '').filter(Boolean).join('. '))
      } else {
        setServerError('Erro ao criar conta. Verifique os dados e tente novamente.')
      }
    },
  })

  const handleChange = (name, value) => {
    const nextForm = { ...form, [name]: value }
    setForm(nextForm)
    if (fieldErrors[name]) {
      const msg = validateField(name, value, nextForm)
      setFieldErrors((prev) => {
        if (!msg) {
          const next = { ...prev }
          delete next[name]
          return next
        }
        return { ...prev, [name]: msg }
      })
    }
    if (name === 'password' && form.confirmPassword) {
      const confirmMsg = validateField('confirmPassword', form.confirmPassword, nextForm)
      setFieldErrors((prev) => {
        if (!confirmMsg) {
          const next = { ...prev }
          delete next.confirmPassword
          return next
        }
        return { ...prev, confirmPassword: confirmMsg }
      })
    }
  }

  const handleBlur = (name) => {
    const msg = validateField(name, form[name], form)
    setFieldErrors((prev) => {
      if (!msg) {
        const next = { ...prev }
        delete next[name]
        return next
      }
      return { ...prev, [name]: msg }
    })
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    setServerError('')
    const errors = validateForm(form)
    setFieldErrors(errors)
    if (Object.keys(errors).length > 0) return
    mutation.mutate(form)
  }

  const fields = [
    {
      name: 'schoolName',
      label: 'Nome da Escola',
      placeholder: 'Ex: Escola Profissional de Lisboa',
      icon: cilInstitution,
    },
    {
      name: 'adminName',
      label: 'Nome do Administrador',
      placeholder: 'Ex: Maria Silva',
      icon: cilUser,
    },
    {
      name: 'email',
      label: 'Email',
      placeholder: 'admin@escola.pt',
      icon: cilEnvelopeClosed,
      type: 'email',
      autoComplete: 'email',
    },
    {
      name: 'password',
      label: 'Password',
      placeholder: `Mínimo ${MIN_PASSWORD_LENGTH} caracteres`,
      icon: cilLockLocked,
      type: 'password',
      autoComplete: 'new-password',
    },
    {
      name: 'confirmPassword',
      label: 'Confirmar Password',
      placeholder: 'Repita a password',
      icon: cilLockLocked,
      type: 'password',
      autoComplete: 'new-password',
    },
  ]

  const validCount = fields.reduce((count, f) => {
    return count + (form[f.name] && !validateField(f.name, form[f.name], form) ? 1 : 0)
  }, 0)

  return (
    <div style={{ display: 'flex', minHeight: '100vh', backgroundColor: 'var(--brand-50)' }}>
      {/* ── FORM SIDE ── */}
      <div style={{
        flex: '1 1 60%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '48px 32px',
        overflowY: 'auto',
      }}>
        <div className="zen-reveal" style={{ width: '100%', maxWidth: '460px' }}>
          {/* Brand mark */}
          <Link to="/" style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '10px',
            textDecoration: 'none',
            marginBottom: '40px',
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
            Criar Conta
          </h1>
          <p style={{
            color: 'var(--brand-600)',
            fontSize: '0.95rem',
            marginBottom: '32px',
            lineHeight: 1.6,
          }}>
            Registe a sua escola e comece a gerir horários em menos de 2 minutos.
            O primeiro utilizador será o administrador da organização.
          </p>

          {serverError && (
            <CAlert color="danger" className="mb-4 py-2 small">
              {serverError}
            </CAlert>
          )}

          <CForm onSubmit={handleSubmit} noValidate>
            {fields.map((field) => (
              <div key={field.name} className="mb-3">
                <label
                  htmlFor={`reg-${field.name}`}
                  className="form-label"
                  style={{
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    color: fieldErrors[field.name] ? 'var(--color-danger)' : 'var(--brand-800)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    marginBottom: '6px',
                  }}
                >
                  {field.label}
                </label>
                <CInputGroup>
                  <CInputGroupText style={{
                    backgroundColor: 'var(--brand-50)',
                    border: `1px solid ${fieldErrors[field.name] ? 'var(--color-danger)' : 'var(--color-border-default)'}`,
                    borderRight: 'none',
                  }}>
                    <CIcon icon={field.icon} size="sm" />
                  </CInputGroupText>
                  <CFormInput
                    id={`reg-${field.name}`}
                    type={field.type || 'text'}
                    placeholder={field.placeholder}
                    autoComplete={field.autoComplete}
                    value={form[field.name]}
                    onChange={(e) => handleChange(field.name, e.target.value)}
                    onBlur={() => handleBlur(field.name)}
                    invalid={!!fieldErrors[field.name]}
                    valid={form[field.name] && !validateField(field.name, form[field.name], form) ? true : undefined}
                    style={{
                      border: `1px solid ${fieldErrors[field.name] ? 'var(--color-danger)' : 'var(--color-border-default)'}`,
                      borderLeft: 'none',
                      fontSize: '0.92rem',
                      padding: '10px 12px',
                    }}
                  />
                  {form[field.name] && !validateField(field.name, form[field.name], form) && (
                    <CInputGroupText style={{
                      backgroundColor: 'var(--brand-50)',
                      border: '1px solid var(--color-state-given)',
                      borderLeft: 'none',
                    }}>
                      <CIcon icon={cilCheckCircle} size="sm" style={{ color: 'var(--color-state-given)' }} />
                    </CInputGroupText>
                  )}
                </CInputGroup>
                {fieldErrors[field.name] && (
                  <CFormFeedback invalid style={{ display: 'block', fontSize: '0.78rem', marginTop: '4px' }}>
                    {fieldErrors[field.name]}
                  </CFormFeedback>
                )}
              </div>
            ))}

            {/* Progress indicator */}
            <div style={{
              marginBottom: '20px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              fontSize: '0.78rem',
              color: 'var(--brand-600)',
            }}>
              <div style={{
                flex: 1,
                height: '3px',
                backgroundColor: 'var(--color-border-default)',
                borderRadius: '2px',
                overflow: 'hidden',
              }}>
                <div style={{
                  height: '100%',
                  width: `${(validCount / fields.length) * 100}%`,
                  backgroundColor: 'var(--brand-800)',
                  borderRadius: '2px',
                  transition: 'width 0.3s ease',
                }} />
              </div>
              <span style={{ whiteSpace: 'nowrap' }}>{validCount}/{fields.length} preenchidos</span>
            </div>

            <CButton
              type="submit"
              className="btn-zen btn-zen-primary w-100 mb-4"
              disabled={mutation.isPending}
              style={{ padding: '12px' }}
            >
              {mutation.isPending ? (
                <><CSpinner size="sm" className="me-2" />A criar conta…</>
              ) : (
                'Criar Conta'
              )}
            </CButton>

            <div style={{ textAlign: 'center' }}>
              <span style={{ color: 'var(--brand-600)', fontSize: '0.88rem' }}>
                Já tem conta?{' '}
              </span>
              <Link to="/login" className="zen-link-underline" style={{
                color: 'var(--brand-800)',
                fontWeight: 600,
                textDecoration: 'none',
                fontSize: '0.88rem',
              }}>
                Entrar
              </Link>
            </div>
          </CForm>
        </div>
      </div>

      {/* ── BRAND PANEL ── */}
      <BrandPanel
        tagline="A sua escola merece um sistema de horários à altura. Simples de configurar, poderoso a operar."
        stats={[
          { value: '<2min', label: 'Configurar' },
          { value: 'Ilimitado', label: 'Professores' },
          { value: 'Grátis', label: 'Sempre' },
        ]}
      />
    </div>
  )
}

export default Register
