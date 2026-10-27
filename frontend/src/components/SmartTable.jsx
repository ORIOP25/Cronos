import { useState } from 'react'
import { CCard, CCardBody } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilPencil, cilTrash, cilChevronRight } from '@coreui/icons'
import { toast } from 'react-hot-toast'
import ConfirmationModal from './ConfirmationModal'
import { TXT } from '../utils/terminology'
import { getApiErrorMessage, isApiErrorBlock } from '../utils/apiErrors'
import { useAttemptScope } from '../hooks/useAttemptScope'
import StatePanel from './StatePanel'
import FeedbackBanner from './FeedbackBanner'
import { BulkRemovalActions, BulkSelectionCheckbox } from './BulkRemoval'
import { useBulkRemoval } from '../hooks/useBulkRemoval'

const RowActions = ({
  item,
  actions,
  isClickable,
  allowEdit,
  allowDelete,
  readOnly,
  onEdit,
  onRequestDelete,
  getRowLabel,
}) => {
  const label = getRowLabel?.(item) ?? item.name ?? ''
  return (
    <td className="text-end">
      <div className="d-flex justify-content-end align-items-center gap-2">
        {actions && (
          <>
            {allowEdit && <button
              className="btn-zen-ghost zen-table-action-trigger"
              onClick={(e) => { e.stopPropagation(); onEdit(item) }}
              title={readOnly ? 'Consultar' : TXT.EDIT}
              data-tutorial-target={`edit-record-${item.id}`}
              aria-label={`${readOnly ? 'Consultar' : TXT.EDIT} ${label}`.trim()}
              type="button"
            >
              <CIcon icon={cilPencil} size="sm"/>
            </button>}
            {allowDelete && <button
              className="btn-zen-ghost zen-table-action-trigger text-danger"
              onClick={(e) => { e.stopPropagation(); onRequestDelete(item) }}
              title={TXT.REMOVE}
              aria-label={`${TXT.REMOVE} ${label}`.trim()}
              type="button"
            >
              <CIcon icon={cilTrash} size="sm"/>
            </button>}
          </>
        )}
        {isClickable && !actions && (
          <CIcon icon={cilChevronRight} size="sm" className="text-muted zen-table-action-trigger" />
        )}
      </div>
    </td>
  )
}

const SmartTable = ({ 
  columns, 
  data, 
  isLoading, 
  isError,
  error,
  onRetry,
  actions, 
  onEdit, 
  onDelete,
  onRowClick,
  getRowLabel,
  emptyAction,
  deleteMessage,
  bulkDeleteMessage = deleteMessage,
  allowEdit = true,
  allowDelete = true,
  readOnly = false,
}) => {
  const isClickable = typeof onRowClick === 'function'
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const attemptScope = useAttemptScope()
  const bulkEnabled = allowDelete && typeof onDelete === 'function'
  const bulk = useBulkRemoval(bulkEnabled ? (data || []) : [], onDelete)

  const handleDeleteConfirm = async () => {
    if (!deleteTarget || !onDelete) return
    const attempt = attemptScope.capture()
    setIsDeleting(true)
    setDeleteError('')
    try {
      const result = await onDelete(deleteTarget.id)
      if (!attemptScope.isCurrent(attempt)) {
        setDeleteTarget(null)
        return
      }
      toast.success(result?.remove_effect === 'archive' ? TXT.RECORD_ARCHIVED : TXT.RECORD_REMOVED)
      setDeleteTarget(null)
    } catch (error) {
      if (!attemptScope.isCurrent(attempt)) {
        setDeleteTarget(null)
        return
      }
      if (isApiErrorBlock(error)) {
        setDeleteError(getApiErrorMessage(error))
        setDeleteTarget(null)
      } else {
        toast.error(getApiErrorMessage(error, 'Não foi possível remover. Tente novamente.'))
      }
    } finally {
      setIsDeleting(false)
    }
  }

  const activateRow = (event, item) => {
    if (!isClickable || event.target.closest('input, label, button, a, select, textarea')) return
    if (event.type === 'keydown') {
      if (!['Enter', ' '].includes(event.key)) return
      event.preventDefault()
    }
    onRowClick(item)
  }
  
  if (isError) {
    const msg = getApiErrorMessage(error, TXT.ERROR_LOADING)
    return <StatePanel state="error" title="Erro ao carregar" description={msg} action={onRetry && <button className="btn btn-outline-primary" type="button" onClick={onRetry}>Tentar novamente</button>} />
  }

  if (isLoading) {
    return <StatePanel state="loading" title={TXT.LOADING} />
  }

  if (!data || data.length === 0) {
    return <StatePanel state="empty" title={TXT.EMPTY_TABLE} description={TXT.EMPTY_TABLE_HINT} action={emptyAction} />
  }

  return (
    <>
      {bulkEnabled && <BulkRemovalActions bulk={bulk} message={bulkDeleteMessage} />}
      <CCard className="border-0 shadow-sm"><CCardBody className="p-0 zen-reveal">
        <table className={`zen-table${bulkEnabled ? ' zen-table--selectable' : ''}`}>
          <thead>
            <tr>
              {bulkEnabled && <th className="selection-column" aria-label="Seleção">
                <BulkSelectionCheckbox label="Selecionar todos" checked={bulk.available.length === data.length} mixed={bulk.available.length > 0 && bulk.available.length < data.length} onChange={bulk.toggleAll} disabled={bulk.pending}>
                  <span className="selection-column__label">Selecionar todos</span>
                </BulkSelectionCheckbox>
              </th>}
              {columns.map((col) => (
                <th key={col.key || col.label} style={col._style}>
                  {col.label}
                </th>
              ))}
              {(actions || isClickable) && <th className="text-end" style={{ width: '120px' }}>{actions ? 'Ações' : ''}</th>}
            </tr>
          </thead>
          <tbody>
            {data.map((item, rowIndex) => (
              <tr 
                key={item.id || rowIndex}
                onClick={isClickable ? (event) => activateRow(event, item) : undefined}
                onKeyDown={isClickable ? (event) => activateRow(event, item) : undefined}
                tabIndex={isClickable ? 0 : undefined}
                aria-label={isClickable ? getRowLabel?.(item) : undefined}
                className={`${isClickable ? 'zen-table-row-interactive' : ''} ${bulk.available.some((selected) => selected.id === item.id) ? 'bulk-selected' : ''}`.trim()}
              >
                {bulkEnabled && <td className="selection-column"><BulkSelectionCheckbox label={`Selecionar ${getRowLabel?.(item) ?? item.name ?? item.id}`} checked={bulk.selected.includes(item.id)} onChange={() => bulk.toggle(item.id)} disabled={bulk.pending} /></td>}
                {columns.map((col) => (
                  <td key={col.key || col.label} data-label={col.label}>
                    {col.render ? col.render(item) : item[col.key]}
                  </td>
                ))}
                
                {(actions || isClickable) && (
                  <RowActions
                    item={item}
                    actions={actions}
                    isClickable={isClickable}
                    allowEdit={allowEdit}
                    allowDelete={allowDelete}
                    readOnly={readOnly}
                    onEdit={onEdit}
                    onRequestDelete={(row) => { setDeleteError(''); setDeleteTarget(row) }}
                    getRowLabel={getRowLabel}
                  />
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </CCardBody></CCard>

      {deleteError && <div className="mt-3"><FeedbackBanner tone="danger">{deleteError}</FeedbackBanner></div>}

      <ConfirmationModal
        visible={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDeleteConfirm}
        message={typeof deleteMessage === 'function' ? deleteTarget && deleteMessage(deleteTarget) : deleteMessage}
        isLoading={isDeleting}
      />
    </>
  )
}

export default SmartTable
