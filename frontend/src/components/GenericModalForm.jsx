import React, { useEffect } from 'react'
import {
  CModal, CModalHeader, CModalTitle, CModalBody, CModalFooter,
  CButton, CAlert
} from '@coreui/react'

/**
 * Componente Genérico para Criar/Editar Entidades via Modal.
 * * @param {boolean} visible - Se o modal está aberto
 * @param {function} onClose - Função para fechar o modal
 * @param {string} title - Título base (ex: "Professor")
 * @param {object} initialData - Dados para edição (se null, é criação)
 * @param {Component} formComponent - O componente do formulário (ex: TeacherForm)
 * @param {function} onSubmit - Função chamada ao submeter (mutate)
 * @param {boolean} isLoading - Estado de loading da mutação
 * @param {object} error - Erro da mutação (para mostrar mensagens do backend)
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

  // Extrair mensagem de erro amigável do backend
  // O FastAPI envia erros em: err.response.data.detail
  const errorMessage = error?.response?.data?.detail || error?.message

  return (
    <CModal visible={visible} onClose={onClose} backdrop="static">
      <CModalHeader onClose={onClose}>
        <CModalTitle>{modalTitle}</CModalTitle>
      </CModalHeader>
      
      <CModalBody>
        {/* Tratamento de Erros (Visão Sénior) */}
        {/* Aqui apanhamos os erros 400 (Dependências) e 409 (Duplicados) */}
        {errorMessage && (
          <CAlert color="danger" dismissible>
            <strong>Erro:</strong> {errorMessage}
          </CAlert>
        )}

        {/* Renderizamos o Formulário Específico */}
        {/* Passamos o onSubmit e o initialData para ele */}
        <FormComponent 
          initialData={initialData} 
          onSubmit={onSubmit} 
          isLoading={isLoading}
          onCancel={onClose}
        />
      </CModalBody>
      
      {/* Removemos o Footer padrão porque os botões de submit devem estar dentro do FormComponent para controlar o estado do form (react-hook-form) */}
    </CModal>
  )
}

export default GenericModalForm