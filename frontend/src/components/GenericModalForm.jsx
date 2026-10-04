import {
  CModal, CModalHeader, CModalTitle, CModalBody,
} from '@coreui/react'
import { getApiErrorMessage } from '../utils/apiErrors'
import { useSlowRequest } from '../utils/useSlowRequest'
import FeedbackBanner from './FeedbackBanner'

/**
 * Componente Genérico para Criar/Editar Entidades via Modal.
 * Uma mutação em curso bloqueia o fecho e explica esperas longas.
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
  readOnly = false,
}) => {

  const isEditing = !!initialData
  const isFeminine = ['Sala', 'Disciplina', 'Turma', 'Configuração'].some((word) => title?.includes(word))
  const prefix = readOnly ? 'Consultar' : isEditing ? 'Editar' : (isFeminine ? 'Nova' : 'Novo')
  const modalTitle = `${prefix} ${title}`
  const isSlowRequest = useSlowRequest(Boolean(isLoading))

  const errorMessage = error ? getApiErrorMessage(error) : null
  const handleClose = () => {
    if (!isLoading) onClose()
  }

  if (!visible) return null

  return (
    <CModal
      className="confirmation-modal"
      visible={visible}
      onClose={handleClose}
      backdrop="static"
      keyboard={!isLoading}
      size={size}
      scrollable
      data-tutorial-target={tutorialTarget}
    >
      <CModalHeader onClose={handleClose}>
        <CModalTitle>{modalTitle}</CModalTitle>
      </CModalHeader>
      
      <CModalBody>
        {errorMessage && (
          <FeedbackBanner tone="danger" onDismiss={handleClose}>Erro: {errorMessage}</FeedbackBanner>
        )}
        {isLoading && (
          <p className="small text-muted mb-2" role="status" aria-live="polite">
            {isSlowRequest
              ? 'A operação continua. Aguarde, por favor.'
              : 'Aguarde, por favor…'}
          </p>
        )}

        <FormComponent 
          initialData={initialData} 
          onSubmit={onSubmit} 
          isLoading={isLoading}
          onCancel={handleClose}
          readOnly={readOnly}
        />
      </CModalBody>
    </CModal>
  )
}

export default GenericModalForm
