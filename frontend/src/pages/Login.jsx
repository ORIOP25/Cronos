// Ficheiro: src/pages/Login.jsx
import React, { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import apiClient from '../apiClient'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '../store'
import { getDefaultRouteForRole } from '../roleAccess'

// UI Components
import {
  CButton, CCard, CCardBody, CCardGroup, CCol, CContainer,
  CForm, CFormInput, CInputGroup, CInputGroupText, CRow, CAlert
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilLockLocked, cilUser } from '@coreui/icons'

const Login = () => {
  const navigate = useNavigate()
  const setLogin = useAuthStore((state) => state.login)
  
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errorMsg, setErrorMsg] = useState('')

  // Mutação do Login
  const mutation = useMutation({
    mutationFn: async (credentials) => {
      // Formato OAuth2 (x-www-form-urlencoded)
      const formData = new URLSearchParams()
      formData.append('username', credentials.email)
      formData.append('password', credentials.password)

      const res = await apiClient.post('/auth/token', formData, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      })
      return res.data
    },
    onSuccess: (data) => {
      // 1. Guardar na Store
      setLogin(data)

      // 2. Redirecionar Inteligente
      navigate(getDefaultRouteForRole(data.role))
    },
    onError: (err) => {
      console.error("Login falhou:", err)
      setErrorMsg('Credenciais inválidas. Tente novamente.')
    }
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    setErrorMsg('')
    mutation.mutate({ email, password })
  }

  return (
    <div className="min-vh-100 d-flex flex-row align-items-center" style={{ backgroundColor: 'var(--rs-body-bg)' }}>
      <CContainer>
        <CRow className="justify-content-center">
          <CCol md={8} lg={7}>
            <CCardGroup>
              <CCard className="p-4" style={{ borderRadius: '12px 0 0 12px', border: '1px solid var(--rs-card-border)' }}>
                <CCardBody>
                  <CForm onSubmit={handleSubmit}>
                    <h1 style={{ color: 'var(--rs-heading)', fontWeight: '700' }}>Bem-vindo</h1>
                    <p style={{ color: 'var(--rs-muted)' }}>Entre na sua conta para continuar</p>
                    
                    {errorMsg && <CAlert color="danger">{errorMsg}</CAlert>}

                    <CInputGroup className="mb-3">
                      <CInputGroupText style={{ backgroundColor: 'var(--rs-input-group-bg)', border: '1px solid var(--rs-input-group-border)' }}>
                        <CIcon icon={cilUser} />
                      </CInputGroupText>
                      <CFormInput 
                        placeholder="Email" 
                        autoComplete="email" 
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                        style={{ border: '1px solid var(--rs-input-group-border)' }}
                      />
                    </CInputGroup>
                    
                    <CInputGroup className="mb-4">
                      <CInputGroupText style={{ backgroundColor: 'var(--rs-input-group-bg)', border: '1px solid var(--rs-input-group-border)' }}>
                        <CIcon icon={cilLockLocked} />
                      </CInputGroupText>
                      <CFormInput 
                        type="password" 
                        placeholder="Password" 
                        autoComplete="current-password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                        style={{ border: '1px solid var(--rs-input-group-border)' }}
                      />
                    </CInputGroup>
                    
                    <CRow>
                      <CCol xs={6}>
                        <CButton type="submit" color="primary" className="px-4" disabled={mutation.isPending}>
                          {mutation.isPending ? 'A entrar...' : 'Login'}
                        </CButton>
                      </CCol>
                      <CCol xs={6} className="text-end">
                        <Link to="/register" style={{ color: 'var(--rs-muted)', textDecoration: 'none', fontSize: '0.9rem' }}>
                          Criar nova conta
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
                    <p style={{ color: 'var(--rs-login-tagline)', fontSize: '0.95rem' }}>Gestão escolar inteligente e sem stress.</p>
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

export default Login