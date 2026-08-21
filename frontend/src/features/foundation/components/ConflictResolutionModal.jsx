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
  onClose,
}) {
  return (
    <CModal visible={isOpen} onClose={onClose} alignment="center" backdrop="static">
      <CModalHeader closeButton>
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
      </CModalBody>
      <CModalFooter className="d-flex justify-content-between">
        <CButton color="secondary" variant="outline" onClick={onClose}>
          Cancelar
        </CButton>
        <div className="d-flex gap-2">
          <CButton color="primary" onClick={onReload}>
            Recarregar Dados Mais Recentes
          </CButton>
        </div>
      </CModalFooter>
    </CModal>
  )
}
