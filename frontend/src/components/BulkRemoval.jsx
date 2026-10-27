import ConfirmationModal from './ConfirmationModal'
import FeedbackBanner from './FeedbackBanner'

export function BulkRemovalActions({ bulk, message }) {
  return <>
    <button type="button" className="btn btn-outline-danger mb-3" disabled={!bulk.available.length || bulk.pending} onClick={() => bulk.setConfirming(true)}>Remover selecionados ({bulk.available.length})</button>
    {bulk.failures.length > 0 && <div className="mb-3"><FeedbackBanner tone="danger">{bulk.failures.map((failure) => <div key={failure}>{failure}</div>)}</FeedbackBanner></div>}
    <ConfirmationModal visible={bulk.confirming} onClose={() => bulk.setConfirming(false)} onConfirm={() => void bulk.remove()} message={<>Remover {bulk.available.length} registo(s)? {Array.isArray(message) ? message.map((text, index) => <span key={index}><br />{text}</span>) : message}</>} isLoading={bulk.pending} />
  </>
}
