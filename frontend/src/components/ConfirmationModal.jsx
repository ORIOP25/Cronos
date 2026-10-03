import {
  CModal,
  CModalHeader,
  CModalTitle,
  CModalBody,
  CModalFooter,
  CButton,
  CSpinner,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilWarning } from '@coreui/icons'
import { TXT } from '../utils/terminology'
import { useSlowRequest } from '../utils/useSlowRequest'

/**
 * Modal de confirmação reutilizável para ações destrutivas.
 * Substitui window.confirm() nativo em toda a aplicação.
 */
const ConfirmationModal = ({
  visible,
  onClose,
  onConfirm,
  title = TXT.CONFIRM_DELETE,
  message = TXT.CONFIRM_DELETE_MESSAGE,
  confirmText = TXT.CONFIRM,
  cancelText = TXT.CANCEL,
  isLoading = false,
  variant = 'danger',
  pendingText = TXT.SAVING,
}) => {
  const isSlowRequest = useSlowRequest(isLoading)

  return (
    <CModal
      className="confirmation-modal"
      visible={visible}
      onClose={() => { if (!isLoading) onClose?.() }}
      alignment="center"
      scrollable
      backdrop={isLoading ? 'static' : true}
      keyboard={!isLoading}
    >
      <CModalHeader>
        <CModalTitle className="d-flex align-items-center gap-2">
          <CIcon icon={cilWarning} className="text-warning" />
          {title}
        </CModalTitle>
      </CModalHeader>
      <CModalBody>
        <p className="confirmation-modal__message">
          {message}
        </p>
        {isLoading && (
          <p className="small text-muted mb-0 mt-2" role="status" aria-live="polite">
            {isSlowRequest
              ? 'O pedido continua em processamento. Aguarde, por favor.'
              : 'Pedido em processamento.'}
          </p>
        )}
      </CModalBody>
      <CModalFooter>
        <CButton color="secondary" variant="outline" onClick={onClose} disabled={isLoading}>
          {cancelText}
        </CButton>
        <CButton color={variant} onClick={onConfirm} disabled={isLoading}>
          {isLoading ? (
            <>
              <CSpinner size="sm" className="me-1" />
              <span>{pendingText}</span>
            </>
          ) : (
            confirmText
          )}
        </CButton>
      </CModalFooter>
    </CModal>
  )
}

export default ConfirmationModal
