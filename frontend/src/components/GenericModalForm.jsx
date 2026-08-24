import {
  CModal, CModalHeader, CModalTitle, CModalBody,
} from '@coreui/react'
import { getApiErrorMessage } from '../utils/apiErrors'
import FeedbackBanner from './FeedbackBanner'

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
  size,
  tutorialTarget,
}) => {

  const isEditing = !!initialData
  const isFeminine = ['Sala', 'Disciplina', 'Turma', 'Configuração'].some((word) => title?.includes(word))
  const prefix = isEditing ? 'Editar' : (isFeminine ? 'Nova' : 'Novo')
  const modalTitle = `${prefix} ${title}`

  const errorMessage = error ? getApiErrorMessage(error) : null

  return (
    <CModal className="confirmation-modal" visible={visible} onClose={onClose} backdrop="static" size={size} scrollable data-tutorial-target={tutorialTarget}>
      <CModalHeader onClose={onClose}>
        <CModalTitle>{modalTitle}</CModalTitle>
      </CModalHeader>
      
      <CModalBody>
        {/* Mostra o erro já tratado (agora é garantidamente uma String) */}
        {errorMessage && (
          <FeedbackBanner tone="danger" onDismiss={onClose}>Erro: {errorMessage}</FeedbackBanner>
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
