import React from 'react'
import {
  CModal, CModalHeader, CModalTitle, CModalBody,
  CAlert
} from '@coreui/react'
import PropTypes from 'prop-types'
import { useFocusTrap } from '../hooks/useFocusTrap'

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
  error,
  size
}) => {

  useFocusTrap(visible)

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
    <CModal visible={visible} onClose={onClose} backdrop="static" size={size}>
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

GenericModalForm.propTypes = {
  visible: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  title: PropTypes.string.isRequired,
  initialData: PropTypes.object,
  FormComponent: PropTypes.elementType.isRequired,
  onSubmit: PropTypes.func.isRequired,
  isLoading: PropTypes.bool,
  error: PropTypes.object,
  size: PropTypes.string,
}

export default GenericModalForm