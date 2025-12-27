import React, { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import apiClient from '../../apiClient'
import {
  CButton, CCol, CForm, CFormInput, CFormSelect, CAlert, CSpinner, CCard, CCardBody
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilPlus, cilRoom } from '@coreui/icons'

// Função API
const createRoom = async (data) => {
  const response = await apiClient.post('/import/room', data)
  return response.data
}

// Opções Válidas (Hardcoded para garantir consistência com a BD)
const ROOM_TYPES = [
  { label: 'Sala de Aula (Normal)', value: 'normal' },
  { label: 'Laboratório (Lab)', value: 'lab' },
  { label: 'Ginásio / Desporto', value: 'gym' }
]

const RoomForm = ({ onSuccessCallback }) => {
  const [name, setName] = useState('')
  const [type, setType] = useState('normal') // Default seguro
  const [successMsg, setSuccessMsg] = useState('')

  const mutation = useMutation({
    mutationFn: createRoom,
    onSuccess: (data) => {
      setSuccessMsg(`Sala "${data.name}" (${data.type}) criada com sucesso!`)
      setName('')
      setType('normal') // Reset ao tipo
      
      if (onSuccessCallback) onSuccessCallback()
      setTimeout(() => setSuccessMsg(''), 3000)
    },
    onError: (error) => {
        // Limpa sucesso se houver erro
        setSuccessMsg('')
    }
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!name.trim()) return
    
    // Envia exatamente os valores que a API espera
    mutation.mutate({ 
        name: name, 
        type: type 
    })
  }

  return (
    <CCard className="border-0 shadow-sm mb-4">
      <CCardBody className="p-4">
        <div className="d-flex align-items-center mb-4">
            <div className="bg-light p-3 rounded-circle me-3 text-primary">
                <CIcon icon={cilRoom} size="xl"/>
            </div>
            <div>
                <h5 className="m-0 fw-bold text-dark">Adicionar Sala</h5>
                <p className="text-muted small m-0">Defina o nome e a tipologia do espaço.</p>
            </div>
        </div>

        {mutation.isError && (
          <CAlert color="danger">
            {mutation.error.response?.data?.detail || 'Erro ao criar sala.'}
          </CAlert>
        )}
        {successMsg && <CAlert color="success">{successMsg}</CAlert>}

        <CForm onSubmit={handleSubmit}>
          <div className="d-flex flex-column flex-md-row gap-3">
            
            {/* 1. NOME DA SALA */}
            <div style={{ flexGrow: 2 }}>
                <CFormInput
                  label="Nome da Sala"
                  type="text"
                  placeholder="Ex: Sala 12 ou Lab. Química"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={mutation.isPending}
                />
            </div>

            {/* 2. TIPO DA SALA (DROPDOWN OBRIGATÓRIO) */}
            <div style={{ flexGrow: 1, minWidth: '200px' }}>
                <CFormSelect 
                    label="Tipo de Espaço"
                    value={type}
                    onChange={(e) => setType(e.target.value)}
                    disabled={mutation.isPending}
                >
                    {ROOM_TYPES.map(opt => (
                        <option key={opt.value} value={opt.value}>
                            {opt.label}
                        </option>
                    ))}
                </CFormSelect>
            </div>
            
            {/* BOTÃO */}
            <div className="d-flex align-items-end">
                <CButton 
                    color="primary" 
                    type="submit" 
                    disabled={mutation.isPending || !name}
                    className="px-4"
                >
                  {mutation.isPending ? <CSpinner size="sm"/> : <><CIcon icon={cilPlus} className="me-2"/> Adicionar</>}
                </CButton>
            </div>
          </div>
        </CForm>
      </CCardBody>
    </CCard>
  )
}

export default RoomForm