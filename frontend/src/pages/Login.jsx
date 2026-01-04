// Ficheiro: src/pages/Login.jsx
import React, { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import apiClient from '../apiClient'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store'

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
      const role = data.role
      if (role === 'admin') {
        navigate('/dashboard')
      } else if (role === 'teacher') {
        navigate('/my-availability')
      } else {
        navigate('/') // Fallback
      }
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
    <div className="bg-light min-vh-100 d-flex flex-row align-items-center">
      <CContainer>
        <CRow className="justify-content-center">
          <CCol md={8}>
            <CCardGroup>
              <CCard className="p-4">
                <CCardBody>
                  <CForm onSubmit={handleSubmit}>
                    <h1>Login</h1>
                    <p className="text-medium-emphasis">Entre na sua conta</p>
                    
                    {errorMsg && <CAlert color="danger">{errorMsg}</CAlert>}

                    <CInputGroup className="mb-3">
                      <CInputGroupText><CIcon icon={cilUser} /></CInputGroupText>
                      <CFormInput 
                        placeholder="Email" 
                        autoComplete="email" 
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                      />
                    </CInputGroup>
                    
                    <CInputGroup className="mb-4">
                      <CInputGroupText><CIcon icon={cilLockLocked} /></CInputGroupText>
                      <CFormInput 
                        type="password" 
                        placeholder="Password" 
                        autoComplete="current-password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                      />
                    </CInputGroup>
                    
                    <CRow>
                      <CCol xs={6}>
                        <CButton type="submit" color="primary" className="px-4" disabled={mutation.isPending}>
                          {mutation.isPending ? 'A entrar...' : 'Login'}
                        </CButton>
                      </CCol>
                    </CRow>
                  </CForm>
                </CCardBody>
              </CCard>
              
              <CCard className="text-white bg-primary py-5" style={{ width: '44%' }}>
                <CCardBody className="text-center d-flex align-items-center justify-content-center">
                  <div>
                    <h2>Horário Zen 🧘</h2>
                    <p>Gestão escolar inteligente e sem stress.</p>
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