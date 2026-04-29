import React from 'react'
import { CSpinner } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilPencil, cilTrash, cilChevronRight } from '@coreui/icons'
import PropTypes from 'prop-types'

const SmartTable = ({ 
  columns, 
  data, 
  isLoading, 
  actions, 
  onEdit, 
  onDelete,
  onRowClick,
}) => {
  const isClickable = typeof onRowClick === 'function'
  
  if (isLoading) {
    return (
      <div className="text-center p-5 zen-reveal">
        <CSpinner color="primary" variant="grow" />
        <p className="text-muted mt-3 text-editorial">A preparar os seus dados...</p>
      </div>
    )
  }

  if (!data || data.length === 0) {
    return (
      <div className="text-center p-5 text-muted zen-reveal">
        <div className="luxury-line" style={{ margin: '0 auto 20px' }} />
        <p className="text-display" style={{ fontSize: '1.2rem' }}>Ainda sem registos.</p>
        <p style={{ fontSize: '0.9rem' }}>Os dados aparecerão aqui assim que forem criados.</p>
      </div>
    )
  }

  return (
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
                          title="Editar"
                        >
                          <CIcon icon={cilPencil} size="sm"/>
                        </button>
                        <button 
                          className="btn-zen-ghost zen-table-action-trigger text-danger"
                          onClick={(e) => { e.stopPropagation(); onDelete(item.id) }}
                          title="Apagar"
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
  actions: PropTypes.bool,
  onEdit: PropTypes.func,
  onDelete: PropTypes.func,
  onRowClick: PropTypes.func,
}

export default SmartTable