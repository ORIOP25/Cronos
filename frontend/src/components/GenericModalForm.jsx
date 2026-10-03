import {
  CModal, CModalHeader, CModalTitle, CModalBody,
} from '@coreui/react'

/**
 * Componente Genérico para Criar/Editar Entidades via Modal.
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

  if (!visible) return null

  return (
    <CModal className="confirmation-modal" visible={visible} onClose={onClose} backdrop="static" size={size} scrollable data-tutorial-target={tutorialTarget}>
      <CModalHeader onClose={onClose}>
        <CModalTitle>{modalTitle}</CModalTitle>
      </CModalHeader>
      
      <CModalBody>
        <FormComponent 
          initialData={initialData} 
          onSubmit={onSubmit} 
          isLoading={isLoading}
          onCancel={onClose}
          readOnly={readOnly}
        />
      </CModalBody>
    </CModal>
  )
}

export default GenericModalForm
