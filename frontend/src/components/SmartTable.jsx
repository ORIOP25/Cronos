import React from 'react'
import {
  CTable, CTableHead, CTableRow, CTableHeaderCell, CTableBody, CTableDataCell,
  CButton, CSpinner
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilPencil, cilTrash } from '@coreui/icons'

const SmartTable = ({ 
  columns, 
  data, 
  isLoading, 
  actions, 
  onEdit, 
  onDelete 
}) => {
  
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
          {columns.map((col, index) => (
            <CTableHeaderCell key={index} style={col._style}>
              {col.label}
            </CTableHeaderCell>
          ))}
          {actions && <CTableHeaderCell className="text-end">Ações</CTableHeaderCell>}
        </CTableRow>
      </CTableHead>
      <CTableBody>
        {data.map((item, rowIndex) => (
          <CTableRow key={item.id || rowIndex}>
            {columns.map((col, colIndex) => (
              <CTableDataCell key={colIndex}>
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
                  onClick={() => onEdit(item)}
                  title="Editar"
                >
                  <CIcon icon={cilPencil} size="sm"/>
                </CButton>
                <CButton 
                  color="light" 
                  size="sm" 
                  className="text-danger"
                  onClick={() => onDelete(item.id)}
                  title="Apagar"
                >
                  <CIcon icon={cilTrash} size="sm"/>
                </CButton>
              </CTableDataCell>
            )}
          </CTableRow>
        ))}
      </CTableBody>
    </CTable>
  )
}

export default SmartTable