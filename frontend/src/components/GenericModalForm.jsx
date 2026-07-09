import React from 'react'
import {
  CModal, CModalHeader, CModalTitle, CModalBody,
  CAlert
} from '@coreui/react'
import PropTypes from 'prop-types'
import { useFocusTrap } from '../hooks/useFocusTrap'
import { getApiErrorMessage } from '../utils/apiErrors'

/**
 * Componente Genérico para Criar/Editar Entidades via Modal.
 */
const GenericModalForm = ({ 
  visible, 
  onClose, 
  title, 
  initialData, 
  FormComponent, // eslint-disable-line no-unused-vars
  onSubmit, 
  isLoading,
  error,
  size
}) => {

  useFocusTrap(visible)

  const isEditing = !!initialData
  const modalTitle = isEditing ? `Editar ${title}` : `Novo ${title}`

  const errorMessage = error ? getApiErrorMessage(error) : null

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
