import { useState } from 'react'
import { CCard, CCardBody } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilPencil, cilTrash, cilChevronRight } from '@coreui/icons'
import ConfirmationModal from './ConfirmationModal'
import { TXT } from '../utils/terminology'
import { getApiErrorMessage } from '../utils/apiErrors'
import StatePanel from './StatePanel'
import FeedbackBanner from './FeedbackBanner'

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
  allowEdit = true,
  allowDelete = true,
  readOnly = false,
}) => {
  const isClickable = typeof onRowClick === 'function'
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')

  const handleDeleteConfirm = async () => {
    if (!deleteTarget || !onDelete) return
    setIsDeleting(true)
    setDeleteError('')
    try {
      await onDelete(deleteTarget)
      setDeleteTarget(null)
    } catch (error) {
      setDeleteError(getApiErrorMessage(error, 'Não foi possível remover o registo.'))
    } finally {
      setIsDeleting(false)
    }
  }

  const activateRow = (event, item) => {
    if (!isClickable || !['Enter', ' '].includes(event.key)) return
    event.preventDefault()
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
      <CCard className="border-0 shadow-sm"><CCardBody className="p-0 zen-reveal">
        <table className="zen-table">
          <thead>
            <tr>
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
                onClick={isClickable ? () => onRowClick(item) : undefined}
                onKeyDown={isClickable ? (event) => activateRow(event, item) : undefined}
                tabIndex={isClickable ? 0 : undefined}
                aria-label={isClickable ? getRowLabel?.(item) : undefined}
                className={isClickable ? 'zen-table-row-interactive' : undefined}
              >
                {columns.map((col) => (
                  <td key={col.key || col.label} data-label={col.label}>
                    {col.render ? col.render(item) : item[col.key]}
                  </td>
                ))}
                
                {(actions || isClickable) && (
                  <td className="text-end">
                    <div className="d-flex justify-content-end align-items-center gap-2">
                      {actions && (
                        <>
                          {allowEdit && <button
                            className="btn-zen-ghost zen-table-action-trigger"
                            onClick={(e) => { e.stopPropagation(); onEdit(item) }}
                            title={readOnly ? 'Consultar' : TXT.EDIT}
                            data-tutorial-target={`edit-record-${item.id}`}
                            aria-label={`${readOnly ? 'Consultar' : TXT.EDIT} ${getRowLabel?.(item) ?? item.name ?? ''}`.trim()}
                            type="button"
                          >
                            <CIcon icon={cilPencil} size="sm"/>
                          </button>}
                          {allowDelete && <button
                            className="btn-zen-ghost zen-table-action-trigger text-danger"
                            onClick={(e) => { e.stopPropagation(); setDeleteError(''); setDeleteTarget(item.id) }}
                            title={TXT.REMOVE}
                            aria-label={`${TXT.REMOVE} ${getRowLabel?.(item) ?? item.name ?? ''}`.trim()}
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
        isLoading={isDeleting}
      />
    </>
  )
}

export default SmartTable
