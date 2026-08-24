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
  conflictData,
  onReload,
  reloadError,
  isReloading = false,
}) {
  return (
    <CModal visible={isOpen} alignment="center" backdrop="static" keyboard={false}>
      <CModalHeader>
        <CModalTitle className="h5 text-warning">
          ⚠️ Conflito de Edição Detetado
        </CModalTitle>
      </CModalHeader>
      <CModalBody>
        <p>
          O rascunho de configuração foi alterado noutro separador ou por outro administrador.
        </p>
        <p className="small text-muted mb-0">
          Versão esperada: <strong>{conflictData?.expected_version ?? '—'}</strong> | Versão no servidor: <strong>{conflictData?.current_version ?? '—'}</strong>
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
