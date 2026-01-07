import React from 'react'
import {
  CModal, CModalHeader, CModalTitle, CModalBody,
  CAlert
} from '@coreui/react'

/**
 * Componente Genérico para Criar/Editar Entidades via Modal.
 */
const GenericModalForm = ({ 
  visible, 
  onClose, 
  title, 
  initialData, 
  FormComponent, 
  onSubmit, 
  isLoading,
  error 
}) => {

  const isEditing = !!initialData
  const modalTitle = isEditing ? `Editar ${title}` : `Novo ${title}`

  // --- TRATAMENTO DE ERROS INTELIGENTE (CORREÇÃO) ---
  let errorMessage = null

  if (error) {
    // 1. Tenta obter o detalhe do backend
    const detail = error.response?.data?.detail

    if (Array.isArray(detail)) {
      // Caso 1: Erro de Validação do Pydantic (Erro 422)
      // O detail é um array de objetos: [{ loc: 'email', msg: 'invalido' }]
      // Vamos juntar todas as mensagens numa string.
      errorMessage = detail.map(err => err.msg).join(', ')
    } else if (typeof detail === 'string') {
      // Caso 2: Erro Simples (Erro 400/404/409 que nós criámos)
      errorMessage = detail
    } else {
      // Caso 3: Fallback (Erro de rede ou desconhecido)
      errorMessage = error.message || "Ocorreu um erro desconhecido."
    }
  }

  return (
    <CModal visible={visible} onClose={onClose} backdrop="static">
      <CModalHeader onClose={onClose}>
        <CModalTitle>{modalTitle}</CModalTitle>
      </CModalHeader>
      
      <CModalBody>
        {/* Mostra o erro já tratado (agora é garantidamente uma String) */}
        {errorMessage && (
          <CAlert color="danger" dismissible>
            <strong>Erro:</strong> {errorMessage}
          </CAlert>
        )}

        <FormComponent 
          initialData={initialData} 
          onSubmit={onSubmit} 
          isLoading={isLoading}
          onCancel={onClose}
        />
      </CModalBody>
    </CModal>
  )
}

export default GenericModalForm