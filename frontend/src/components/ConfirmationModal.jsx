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
}) => {
  return (
    <CModal visible={visible} onClose={onClose} alignment="center">
      <CModalHeader>
        <CModalTitle className="d-flex align-items-center gap-2">
          <CIcon icon={cilWarning} className="text-warning" />
          {title}
        </CModalTitle>
      </CModalHeader>
      <CModalBody>
        <p style={{ color: 'var(--brand-950)', fontSize: '0.95rem', lineHeight: 1.6, margin: 0 }}>
          {message}
        </p>
      </CModalBody>
      <CModalFooter>
        <CButton color="secondary" variant="outline" onClick={onClose} disabled={isLoading}>
          {cancelText}
        </CButton>
        <CButton color={variant} onClick={onConfirm} disabled={isLoading}>
          {isLoading ? (
            <>
              <CSpinner size="sm" className="me-1" />
              <span>{TXT.SAVING}</span>
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
