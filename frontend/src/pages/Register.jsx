// Ficheiro: src/pages/Register.jsx
import React, { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import apiClient from '../apiClient'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '../store'

import {
  CButton, CCard, CCardBody, CCardGroup, CCol, CContainer,
  CForm, CFormInput, CInputGroup, CInputGroupText, CRow, CAlert,
  CFormFeedback,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilLockLocked, cilUser, cilInstitution, cilEnvelopeClosed } from '@coreui/icons'

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/** Validates all fields and returns an error map. Empty map = valid. */
function validateForm({ schoolName, adminName, email, password, confirmPassword }) {
  const errors = {}
  if (!schoolName || schoolName.trim().length < 2) {
    errors.schoolName = 'O nome da escola deve ter pelo menos 2 caracteres.'
  }
  if (!adminName || adminName.trim().length < 2) {
    errors.adminName = 'O nome do administrador deve ter pelo menos 2 caracteres.'
  }
  if (!email || !EMAIL_REGEX.test(email)) {
    errors.email = 'Introduza um e-mail válido.'
  }
  if (!password || password.length < 6) {
    errors.password = 'A password deve ter pelo menos 6 caracteres.'
  }
  if (password !== confirmPassword) {
    errors.confirmPassword = 'As passwords não coincidem.'
  }
  return errors
}

const Register = () => {
  const navigate = useNavigate()
  const setLogin = useAuthStore((state) => state.login)

  const [schoolName, setSchoolName] = useState('')
  const [adminName, setAdminName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
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
      if (detail) {
        setServerError(detail)
      } else {
        setServerError('Erro ao criar conta. Tente novamente.')
      }
    },
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    setServerError('')

    const errors = validateForm({ schoolName, adminName, email, password, confirmPassword })
    setFieldErrors(errors)

    if (Object.keys(errors).length > 0) return

    mutation.mutate({ schoolName, adminName, email, password })
  }

  return (
    <div className="min-vh-100 d-flex flex-row align-items-center" style={{ backgroundColor: 'var(--rs-body-bg)' }}>
      <CContainer>
        <CRow className="justify-content-center">
          <CCol md={9} lg={8}>
            <CCardGroup>
              <CCard className="p-4" style={{ borderRadius: '12px 0 0 12px', border: '1px solid var(--rs-card-border)' }}>
                <CCardBody>
                  <CForm onSubmit={handleSubmit} noValidate>
                    <h1 style={{ color: 'var(--rs-heading)', fontWeight: '700' }}>Criar Conta</h1>
                    <p style={{ color: 'var(--rs-muted)' }}>Registe a sua escola para começar</p>

                    {serverError && <CAlert color="danger">{serverError}</CAlert>}

                    {/* Nome da Escola */}
                    <CInputGroup className="mb-3">
                      <CInputGroupText style={{ backgroundColor: 'var(--rs-input-group-bg)', border: '1px solid var(--rs-input-group-border)' }}>
                        <CIcon icon={cilInstitution} />
                      </CInputGroupText>
                      <CFormInput
                        placeholder="Nome da Escola / Instituição"
                        value={schoolName}
                        onChange={(e) => setSchoolName(e.target.value)}
                        invalid={!!fieldErrors.schoolName}
                        style={{ border: '1px solid var(--rs-input-group-border)' }}
                      />
                      {fieldErrors.schoolName && <CFormFeedback invalid>{fieldErrors.schoolName}</CFormFeedback>}
                    </CInputGroup>

                    {/* Nome do Admin */}
                    <CInputGroup className="mb-3">
                      <CInputGroupText style={{ backgroundColor: 'var(--rs-input-group-bg)', border: '1px solid var(--rs-input-group-border)' }}>
                        <CIcon icon={cilUser} />
                      </CInputGroupText>
                      <CFormInput
                        placeholder="Nome do Administrador"
                        value={adminName}
                        onChange={(e) => setAdminName(e.target.value)}
                        invalid={!!fieldErrors.adminName}
                        style={{ border: '1px solid var(--rs-input-group-border)' }}
                      />
                      {fieldErrors.adminName && <CFormFeedback invalid>{fieldErrors.adminName}</CFormFeedback>}
                    </CInputGroup>

                    {/* Email */}
                    <CInputGroup className="mb-3">
                      <CInputGroupText style={{ backgroundColor: 'var(--rs-input-group-bg)', border: '1px solid var(--rs-input-group-border)' }}>
                        <CIcon icon={cilEnvelopeClosed} />
                      </CInputGroupText>
                      <CFormInput
                        type="email"
                        placeholder="Email"
                        autoComplete="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        invalid={!!fieldErrors.email}
                        style={{ border: '1px solid var(--rs-input-group-border)' }}
                      />
                      {fieldErrors.email && <CFormFeedback invalid>{fieldErrors.email}</CFormFeedback>}
                    </CInputGroup>

                    {/* Password */}
                    <CInputGroup className="mb-3">
                      <CInputGroupText style={{ backgroundColor: 'var(--rs-input-group-bg)', border: '1px solid var(--rs-input-group-border)' }}>
                        <CIcon icon={cilLockLocked} />
                      </CInputGroupText>
                      <CFormInput
                        type="password"
                        placeholder="Password"
                        autoComplete="new-password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        invalid={!!fieldErrors.password}
                        style={{ border: '1px solid var(--rs-input-group-border)' }}
                      />
                      {fieldErrors.password && <CFormFeedback invalid>{fieldErrors.password}</CFormFeedback>}
                    </CInputGroup>

                    {/* Confirmar Password */}
                    <CInputGroup className="mb-4">
                      <CInputGroupText style={{ backgroundColor: 'var(--rs-input-group-bg)', border: '1px solid var(--rs-input-group-border)' }}>
                        <CIcon icon={cilLockLocked} />
                      </CInputGroupText>
                      <CFormInput
                        type="password"
                        placeholder="Confirmar Password"
                        autoComplete="new-password"
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        invalid={!!fieldErrors.confirmPassword}
                        style={{ border: '1px solid var(--rs-input-group-border)' }}
                      />
                      {fieldErrors.confirmPassword && <CFormFeedback invalid>{fieldErrors.confirmPassword}</CFormFeedback>}
                    </CInputGroup>

                    <CRow className="align-items-center">
                      <CCol xs={6}>
                        <CButton type="submit" color="primary" className="px-4" disabled={mutation.isPending}>
                          {mutation.isPending ? 'A criar...' : 'Criar Conta'}
                        </CButton>
                      </CCol>
                      <CCol xs={6} className="text-end">
                        <Link to="/login" style={{ color: 'var(--rs-muted)', textDecoration: 'none', fontSize: '0.9rem' }}>
                          Já tem conta? Entrar
                        </Link>
                      </CCol>
                    </CRow>
                  </CForm>
                </CCardBody>
              </CCard>

              <CCard
                className="text-white py-5"
                style={{
                  width: '44%',
                  background: 'linear-gradient(135deg, var(--rs-login-right-start) 0%, var(--rs-login-right-end) 100%)',
                  borderRadius: '0 12px 12px 0',
                  border: 'none',
                }}>
                <CCardBody className="text-center d-flex align-items-center justify-content-center">
                  <div>
                    <h2 style={{ fontWeight: '700', letterSpacing: '-0.5px' }}>Horário Zen</h2>
                    <p style={{ color: 'var(--rs-login-tagline)', fontSize: '0.95rem' }}>
                      Gestão escolar inteligente e sem stress.
                    </p>
                  </div>
                </CCardBody>
              </CCard>
            </CCardGroup>
          </CCol>
        </CRow>
      </CContainer>
    </div>
  )
}

export default Register
