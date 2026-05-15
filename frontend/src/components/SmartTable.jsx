import React, { useState } from 'react'
import { CSpinner } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilPencil, cilTrash, cilChevronRight } from '@coreui/icons'
import PropTypes from 'prop-types'
import ConfirmationModal from './ConfirmationModal'
import { TXT } from '../utils/terminology'

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
}) => {
  const isClickable = typeof onRowClick === 'function'
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const handleDeleteConfirm = async () => {
    if (!deleteTarget || !onDelete) return
    setIsDeleting(true)
    try {
      await onDelete(deleteTarget)
    } finally {
      setIsDeleting(false)
      setDeleteTarget(null)
    }
  }
  
  if (isError) {
    const msg = error?.response?.data?.detail || error?.message || 'Erro ao carregar os dados'
    return (
      <div className="text-center p-5 zen-reveal">
        <div style={{ color: 'var(--color-state-gap-text)', marginBottom: '16px', fontSize: '2rem' }}>!</div>
        <p className="text-display" style={{ fontSize: '1.1rem', marginBottom: '8px' }}>Erro ao carregar</p>
        <p style={{ color: 'var(--brand-600)', fontSize: '0.9rem', maxWidth: 400, margin: '0 auto 16px' }}>{msg}</p>
        {onRetry && (
          <button className="btn-zen btn-zen-outline" onClick={onRetry}>Tentar novamente</button>
        )}
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="text-center p-5 zen-reveal">
        <CSpinner color="primary" variant="grow" />
        <p className="text-muted mt-3 text-editorial">{TXT.LOADING}</p>
      </div>
    )
  }

  if (!data || data.length === 0) {
    return (
      <div className="text-center p-5 text-muted zen-reveal">
        <div className="luxury-line" style={{ margin: '0 auto 20px' }} />
        <p className="text-display" style={{ fontSize: '1.2rem' }}>{TXT.EMPTY_TABLE}</p>
        <p style={{ fontSize: '0.9rem' }}>{TXT.EMPTY_TABLE_HINT}</p>
      </div>
    )
  }

  return (
    <>
      <div className="zen-reveal">
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
                style={isClickable ? { cursor: 'pointer' } : undefined}
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
                            type="button"
                          >
                            <CIcon icon={cilPencil} size="sm"/>
                          </button>
                          <button 
                            className="btn-zen-ghost zen-table-action-trigger text-danger"
                            onClick={(e) => { e.stopPropagation(); setDeleteTarget(item.id) }}
                            title={TXT.REMOVE}
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
      </div>

      <ConfirmationModal
        visible={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDeleteConfirm}
        isLoading={isDeleting}
      />
    </>
  )
}

SmartTable.propTypes = {
  columns: PropTypes.arrayOf(PropTypes.shape({
    key: PropTypes.string,
    label: PropTypes.string.isRequired,
    _style: PropTypes.object,
    render: PropTypes.func,
  })).isRequired,
  data: PropTypes.array,
  isLoading: PropTypes.bool,
  isError: PropTypes.bool,
  error: PropTypes.object,
  onRetry: PropTypes.func,
  actions: PropTypes.bool,
  onEdit: PropTypes.func,
  onDelete: PropTypes.func,
  onRowClick: PropTypes.func,
}

export default SmartTable
