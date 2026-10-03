import {
  CModal, CModalHeader, CModalTitle, CModalBody,
} from '@coreui/react'
import { useSlowRequest } from '../utils/useSlowRequest'

/**
 * Componente Genérico para Criar/Editar Entidades via Modal.
 * Uma mutação em curso bloqueia o fecho e explica esperas longas.
 * O resultado da tentativa é comunicado pelo dono da mutação.
 */
const GenericModalForm = ({ 
  visible, 
  onClose, 
  title, 
  initialData, 
  FormComponent,
  onSubmit, 
  isLoading,
  size,
  tutorialTarget,
  readOnly = false,
}) => {

  const isEditing = !!initialData
  const isFeminine = ['Sala', 'Disciplina', 'Turma', 'Configuração'].some((word) => title?.includes(word))
  const prefix = readOnly ? 'Consultar' : isEditing ? 'Editar' : (isFeminine ? 'Nova' : 'Novo')
  const modalTitle = `${prefix} ${title}`
  const isSlowRequest = useSlowRequest(Boolean(isLoading))

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
        {isLoading && (
          <p className="small text-muted mb-2" role="status" aria-live="polite">
            {isSlowRequest
              ? 'O pedido continua em processamento. Aguarde, por favor.'
              : 'Pedido em processamento.'}
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
