import React, { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import apiClient from '../apiClient'

// Ferramentas de Navegação e Estado Global
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store'

// Componentes de UI (CoreUI)
import {
  CButton,
  CCard,
  CCardBody,
  CCardGroup,
  CCol,
  CContainer,
  CForm,
  CFormInput,
  CInputGroup,
  CInputGroupText,
  CRow,
  CAlert,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilLockLocked, cilUser } from '@coreui/icons'

// ==========================================
// 1. FUNÇÃO DE SERVIÇO (API)
// ==========================================
const loginUser = async ({ email, password }) => {
  // O FastAPI (OAuth2) exige dados em formato de formulário, não JSON.
  const formData = new URLSearchParams()
  formData.append('username', email) // Mapeamos email -> username
  formData.append('password', password)

  const response = await apiClient.post('/auth/token', formData, {
    headers: {
      // CRÍTICO: Sobrescrevemos o 'application/json' global para este pedido específico
      'Content-Type': 'application/x-www-form-urlencoded',
    },
  })
  return response.data
}

// ==========================================
// 2. COMPONENTE VISUAL
// ==========================================
const Login = () => {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  
  const navigate = useNavigate()
  const setToken = useAuthStore((state) => state.setLogin) // Função para guardar o token

  // Configuração da Mutação (React Query)
  const mutation = useMutation({
    mutationFn: loginUser,
    onSuccess: (data) => {
      console.log('✅ Login efetuado com sucesso!')
      
      // 1. Guardar o token na Store (Zustand)
      setToken(
        data.access_token,
        data.role || 'user',
        email,
        data.teacher_id
      ) // Guardamos também a role se existir

      // 2. Redirecionar para a Dashboard
      navigate('/dashboard')
    },
    onError: (error) => {
      console.error('❌ Erro no login:', error)
      // O erro é tratado visualmente abaixo, não precisamos de fazer alert aqui
    },
  })

  // Função para extrair mensagem de erro legível (Evita o Crash do React)
  const getErrorMessage = (error) => {
    if (!error) return null;
    
    // Tenta ler a mensagem enviada pelo Backend (ex: "Email ou password incorretos")
    if (error.response?.data?.detail) {
        return error.response.data.detail;
    }
    
    // Tenta ler mensagem genérica do Axios
    if (error.message) {
        return error.message;
    }

    return "Erro desconhecido ao tentar entrar.";
  }

  // Submissão do Formulário
  const handleSubmit = (e) => {
    e.preventDefault()
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
                    
                    {/* ZONA DE ERROS BLINDADA */}
                    {mutation.isError && (
                      <CAlert color="danger" className="mb-4">
                        {getErrorMessage(mutation.error)}
                      </CAlert>
                    )}

                    <CInputGroup className="mb-3">
                      <CInputGroupText>
                        <CIcon icon={cilUser} />
                      </CInputGroupText>
                      <CFormInput
                        placeholder="Email"
                        autoComplete="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                      />
                    </CInputGroup>
                    
                    <CInputGroup className="mb-4">
                      <CInputGroupText>
                        <CIcon icon={cilLockLocked} />
                      </CInputGroupText>
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
                        <CButton
                          type="submit"
                          color="primary"
                          className="px-4"
                          disabled={mutation.isPending}
                        >
                          {mutation.isPending ? 'A entrar...' : 'Login'}
                        </CButton>
                      </CCol>
                    </CRow>
                  </CForm>
                </CCardBody>
              </CCard>
              
              {/* Lado Direito (Decorativo - Opcional) */}
              <CCard className="text-white bg-primary py-5" style={{ width: '44%' }}>
                <CCardBody className="text-center">
                  <div>
                    <h2>Horário Zen</h2>
                    <p>
                      Gestão de horários escolar simplificada, rápida e inteligente.
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

export default Login