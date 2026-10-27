import CIcon from '@coreui/icons-react'
import { cilTrash, cilX } from '@coreui/icons'
import ConfirmationModal from './ConfirmationModal'
import FeedbackBanner from './FeedbackBanner'

export function BulkSelectionCheckbox({ label, checked, mixed = false, disabled, onChange, children }) {
  return (
    <label className="bulk-selection" title={label}>
      <input
        type="checkbox"
        className="form-check-input"
        aria-label={label}
        checked={checked}
        ref={(input) => { if (input) input.indeterminate = mixed }}
        disabled={disabled}
        onChange={onChange}
      />
      {children}
    </label>
  )
}

export function BulkRemovalActions({ bulk, message }) {
  const count = bulk.available.length
  const clearSelection = (event) => {
    const selectionInput = event.currentTarget.closest('.bulk-selection-toolbar').parentElement.querySelector('.bulk-selection input:not(:disabled)')
    bulk.clearSelection()
    selectionInput?.focus()
  }
  return (
    <>
      {count > 0 && (
        <section className="bulk-selection-toolbar" aria-label="Ações da seleção">
          <output className="fw-semibold" aria-live="polite">{count} {count === 1 ? 'selecionado' : 'selecionados'}</output>
          <div className="d-flex flex-wrap justify-content-end gap-2">
            <button type="button" className="btn btn-outline-secondary btn-sm" aria-label="Limpar seleção" title="Limpar seleção" disabled={bulk.pending} onClick={clearSelection}>
              <CIcon icon={cilX} aria-hidden="true" />
            </button>
            <button type="button" className="btn btn-outline-danger btn-sm" aria-label="Remover selecionados" disabled={bulk.pending} onClick={() => bulk.setConfirming(true)}>
              <CIcon icon={cilTrash} className="me-2" aria-hidden="true" />Remover
            </button>
          </div>
        </section>
      )}
      {bulk.failures.length > 0 && (
        <div className="mb-3">
          <FeedbackBanner tone="danger" title={`${bulk.failures.length} ${bulk.failures.length === 1 ? 'registo não removido' : 'registos não removidos'}`}>
            <details className="context-details" open>
              <summary>Ver motivos</summary>
              <ul className="mb-0 mt-2">{bulk.failures.map((failure) => <li key={failure}>{failure}</li>)}</ul>
            </details>
          </FeedbackBanner>
        </div>
      )}
      <ConfirmationModal
        visible={bulk.confirming}
        onClose={() => bulk.setConfirming(false)}
        onConfirm={() => void bulk.remove()}
        title="Remover selecionados"
        confirmText="Remover"
        pendingText="A remover…"
        message={(
          <>
            <p className="mb-2">Confirme a remoção de {count} {count === 1 ? 'registo' : 'registos'}.</p>
            {typeof message !== 'function' && message && <p className="small text-muted mb-0">{message}</p>}
            <ul className="bulk-removal-records" aria-label="Registos selecionados">
              {bulk.available.map((item) => (
                <li key={item.id}>
                  <strong>{item.name}</strong>
                  {typeof message === 'function' && <p className="small text-muted mb-0">{message(item)}</p>}
                </li>
              ))}
            </ul>
          </>
        )}
        isLoading={bulk.pending}
      />
    </>
  )
}
