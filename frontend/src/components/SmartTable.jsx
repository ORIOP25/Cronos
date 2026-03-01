import React from 'react'
import {
  CTable, CTableHead, CTableRow, CTableHeaderCell, CTableBody, CTableDataCell,
  CButton, CSpinner
} from '@coreui/react'
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
      <div className="text-center p-4">
        <CSpinner color="primary" />
        <p className="text-muted mt-2">A carregar dados...</p>
      </div>
    )
  }

  if (!data || data.length === 0) {
    return <div className="text-center p-4 text-muted">Não há dados para mostrar.</div>
  }

  return (
    <CTable hover responsive className="align-middle mb-0 border">
      <CTableHead color="light">
        <CTableRow>
          {columns.map((col) => (
            <CTableHeaderCell key={col.key || col.label} style={col._style}>
              {col.label}
            </CTableHeaderCell>
          ))}
          {actions && <CTableHeaderCell className="text-end">Ações</CTableHeaderCell>}
          {isClickable && !actions && <CTableHeaderCell style={{ width: '40px' }} />}
        </CTableRow>
      </CTableHead>
      <CTableBody>
        {data.map((item, rowIndex) => (
          <CTableRow 
            key={item.id || rowIndex}
            onClick={isClickable ? () => onRowClick(item) : undefined}
            style={isClickable ? { cursor: 'pointer' } : undefined}
            className={isClickable ? 'smart-table-clickable' : ''}
          >
            {columns.map((col) => (
              <CTableDataCell key={col.key || col.label}>
                {/* AQUI ESTÁ A CORREÇÃO MÁGICA:
                   Se a coluna tiver uma função 'render', executa-a.
                   Caso contrário, mostra o valor direto.
                */}
                {col.render ? col.render(item) : item[col.key]}
              </CTableDataCell>
            ))}
            
            {actions && (
              <CTableDataCell className="text-end">
                <CButton 
                  color="light" 
                  size="sm" 
                  className="me-2 text-primary"
                  onClick={(e) => { e.stopPropagation(); onEdit(item) }}
                  title="Editar"
                >
                  <CIcon icon={cilPencil} size="sm"/>
                </CButton>
                <CButton 
                  color="light" 
                  size="sm" 
                  className="text-danger"
                  onClick={(e) => { e.stopPropagation(); onDelete(item.id) }}
                  title="Apagar"
                >
                  <CIcon icon={cilTrash} size="sm"/>
                </CButton>
              </CTableDataCell>
            )}

            {isClickable && !actions && (
              <CTableDataCell className="text-end pe-3">
                <CIcon icon={cilChevronRight} size="sm" className="text-muted" />
              </CTableDataCell>
            )}
          </CTableRow>
        ))}
      </CTableBody>
    </CTable>
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