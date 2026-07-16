import {
  CModal, CModalHeader, CModalTitle, CModalBody,
  CAlert
} from '@coreui/react'
import { getApiErrorMessage } from '../utils/apiErrors'

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

export default GenericModalForm
