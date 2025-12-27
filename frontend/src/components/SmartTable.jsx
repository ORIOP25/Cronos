import React from 'react'
import {
  CTable, CTableHead, CTableRow, CTableHeaderCell, CTableBody, CTableDataCell, CButton, CSpinner
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilTrash } from '@coreui/icons'

// Este componente recebe:
// - columns: Array de objetos { key: 'name', label: 'Nome' }
// - data: Array de dados
// - onDelete: Função para apagar (recebe o ID)
// - loading: Booleano
const SmartTable = ({ columns, data, onDelete, isLoading }) => {
  
  if (isLoading) return <div className="text-center p-3"><CSpinner size="sm"/> A carregar lista...</div>
  
  if (!data || data.length === 0) {
    return <div className="text-center p-3 text-muted border rounded bg-light">Nenhum registo encontrado.</div>
  }

  return (
    <div className="border rounded overflow-hidden">
      <CTable hover responsive className="mb-0">
        <CTableHead color="light">
          <CTableRow>
            {columns.map((col, index) => (
              <CTableHeaderCell key={index}>{col.label}</CTableHeaderCell>
            ))}
            <CTableHeaderCell className="text-end" style={{width: '100px'}}>Ações</CTableHeaderCell>
          </CTableRow>
        </CTableHead>
        <CTableBody>
          {data.map((item) => (
            <CTableRow key={item.id}>
              {columns.map((col, index) => (
                <CTableDataCell key={index}>
                  {item[col.key]}
                </CTableDataCell>
              ))}
              <CTableDataCell className="text-end">
                <CButton 
                  color="danger" 
                  variant="ghost" 
                  size="sm"
                  onClick={() => {
                    if(window.confirm('Tem a certeza?')) onDelete(item.id)
                  }}
                >
                  <CIcon icon={cilTrash} />
                </CButton>
              </CTableDataCell>
            </CTableRow>
          ))}
        </CTableBody>
      </CTable>
    </div>
  )
}

export default SmartTable