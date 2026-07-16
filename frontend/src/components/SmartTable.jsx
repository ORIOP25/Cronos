import { useState } from 'react'
import { CAlert, CCard, CCardBody, CSpinner } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilPencil, cilTrash, cilChevronRight } from '@coreui/icons'
import ConfirmationModal from './ConfirmationModal'
import { TXT } from '../utils/terminology'
import { getApiErrorMessage } from '../utils/apiErrors'

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
    return (
      <CCard className="border-0 shadow-sm"><CCardBody className="text-center p-5 zen-reveal">
        <div style={{ color: 'var(--color-state-gap-text)', marginBottom: '16px', fontSize: '2rem' }}>!</div>
        <p className="text-display" style={{ fontSize: '1.1rem', marginBottom: '8px' }}>Erro ao carregar</p>
        <p style={{ color: 'var(--brand-600)', fontSize: '0.9rem', maxWidth: 400, margin: '0 auto 16px' }}>{msg}</p>
        {onRetry && (
          <button className="btn-zen btn-zen-outline" onClick={onRetry}>Tentar novamente</button>
        )}
      </CCardBody></CCard>
    )
  }

  if (isLoading) {
    return (
      <CCard className="border-0 shadow-sm"><CCardBody className="text-center p-5 zen-reveal">
        <CSpinner color="primary" variant="grow" />
        <p className="text-muted mt-3 text-editorial">{TXT.LOADING}</p>
      </CCardBody></CCard>
    )
  }

  if (!data || data.length === 0) {
    return (
      <CCard className="border-0 shadow-sm"><CCardBody className="text-center p-5 text-muted zen-reveal">
        <div className="luxury-line" style={{ margin: '0 auto 20px' }} />
        <p className="text-display" style={{ fontSize: '1.2rem' }}>{TXT.EMPTY_TABLE}</p>
        <p style={{ fontSize: '0.9rem' }}>{TXT.EMPTY_TABLE_HINT}</p>
      </CCardBody></CCard>
    )
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
                  <td key={col.key || col.label}>
                    {col.render ? col.render(item) : item[col.key]}
                  </td>
                ))}
                
                {(actions || isClickable) && (
                  <td className="text-end">
                    <div className="d-flex justify-content-end align-items-center gap-2">
                      {actions && (
                        <>
                          <button 
                            className="btn-zen-ghost zen-table-action-trigger"
                            onClick={(e) => { e.stopPropagation(); onEdit(item) }}
                            title={TXT.EDIT}
                            aria-label={`${TXT.EDIT} ${getRowLabel?.(item) ?? item.name ?? ''}`.trim()}
                            type="button"
                          >
                            <CIcon icon={cilPencil} size="sm"/>
                          </button>
                          <button 
                            className="btn-zen-ghost zen-table-action-trigger text-danger"
                            onClick={(e) => { e.stopPropagation(); setDeleteError(''); setDeleteTarget(item.id) }}
                            title={TXT.REMOVE}
                            aria-label={`${TXT.REMOVE} ${getRowLabel?.(item) ?? item.name ?? ''}`.trim()}
                            type="button"
                          >
                            <CIcon icon={cilTrash} size="sm"/>
                          </button>
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

      {deleteError && <CAlert color="danger" className="mt-3">{deleteError}</CAlert>}

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
