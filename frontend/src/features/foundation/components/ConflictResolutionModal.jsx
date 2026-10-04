import {
  CModal,
  CModalHeader,
  CModalTitle,
  CModalBody,
  CModalFooter,
  CButton,
} from '@coreui/react'

export function ConflictResolutionModal({
  isOpen,
  onReload,
  reloadError,
  isReloading = false,
}) {
  return (
    <CModal visible={isOpen} alignment="center" backdrop="static" keyboard={false}>
      <CModalHeader>
        <CModalTitle className="h5 text-warning">
          ⚠️ Estes dados foram alterados
        </CModalTitle>
      </CModalHeader>
      <CModalBody>
        <p>
          Outra pessoa alterou estes dados entretanto. Recarregue para continuar com a versão mais recente.
        </p>
        {reloadError && <div className="alert alert-danger mt-3 mb-0" role="alert">{reloadError}</div>}
      </CModalBody>
      <CModalFooter className="d-flex justify-content-end">
        <CButton color="primary" onClick={onReload} disabled={isReloading}>
          {isReloading ? 'A recarregar…' : 'Recarregar dados mais recentes'}
        </CButton>
      </CModalFooter>
    </CModal>
  )
}
