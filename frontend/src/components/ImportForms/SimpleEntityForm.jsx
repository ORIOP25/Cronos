import React, { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  CButton, CCol, CForm, CFormInput, CAlert, CSpinner, CCard, CCardBody
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilPlus, cilCheckCircle, cilWarning } from '@coreui/icons'

// Adicionámos 'onSuccessCallback' às props recebidas
const SimpleEntityForm = ({ title, subtitle, inputLabel, mutationFn, icon, onSuccessCallback }) => {
  const [name, setName] = useState('')
  const [successMsg, setSuccessMsg] = useState('')

  const mutation = useMutation({
    mutationFn: mutationFn,
    onSuccess: (data) => {
      // 1. Mostrar mensagem de sucesso
      setSuccessMsg(`${inputLabel} "${data.name}" criado(a) com sucesso!`)
      setName('') // Limpar o input
      
      // 2. AVISAR O PAI PARA ATUALIZAR A LISTA (A Correção Principal)
      if (onSuccessCallback) {
        onSuccessCallback()
      }

      // 3. Esconder a mensagem passados 3 segundos
      setTimeout(() => setSuccessMsg(''), 3000)
    },
    onError: (error) => {
        // Se houver erro, garantimos que a mensagem de sucesso está limpa
        setSuccessMsg('') 
    }
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!name.trim()) return

    // --- LIMPEZA DE ESTADO (Correção das mensagens duplas) ---
    setSuccessMsg('') // Limpa sucessos antigos
    mutation.reset()  // Limpa erros antigos (isError volta a false)
    // ---------------------------------------------------------

    mutation.mutate({ name: name })
  }

  return (
    <CCard className="border-0 shadow-sm">
      <CCardBody className="p-4">
        <div className="d-flex align-items-center mb-4">
            <div className="bg-light p-3 rounded-circle me-3 text-primary">
                <CIcon icon={icon} size="xl"/>
            </div>
            <div>
                <h5 className="m-0 fw-bold text-dark">{title}</h5>
                <p className="text-muted small m-0">{subtitle}</p>
            </div>
        </div>
        
        {/* Bloco de ERRO */}
        {mutation.isError && (
          <CAlert color="danger" className="d-flex align-items-center">
            <CIcon icon={cilWarning} className="me-2" />
            {mutation.error.response?.data?.detail || 'Erro ao criar registo.'}
          </CAlert>
        )}
        
        {/* Bloco de SUCESSO (Só aparece se houver mensagem) */}
        {successMsg && (
          <CAlert color="success" className="d-flex align-items-center">
            <CIcon icon={cilCheckCircle} className="me-2" />
            {successMsg}
          </CAlert>
        )}

        <CForm onSubmit={handleSubmit} className="mt-4">
          <div className="d-flex flex-column flex-md-row gap-3">
            <div style={{ flexGrow: 1, maxWidth: '500px' }}>
                <CFormInput
                  type="text"
                  placeholder={`Escreva aqui...`}
                  label={inputLabel}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={mutation.isPending}
                  size="lg"
                />
            </div>
            
            <div className="d-flex align-items-end">
                <CButton 
                    color="primary" 
                    type="submit" 
                    size="lg" 
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

export default SimpleEntityForm