import React from 'react'
import {
  CTable, CTableHead, CTableRow, CTableHeaderCell, CTableBody, CTableDataCell, CButton, CSpinner, CTooltip
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilTrash, cilPencil } from '@coreui/icons'

// Props atualizadas:
// - actions: boolean (Se true, mostra a coluna de editar/apagar)
// - onEdit: Função que recebe o item para editar
// - onDelete: Função que recebe o ID para apagar
const SmartTable = ({ columns, data, onDelete, onEdit, isLoading, actions = false }) => {
  
  if (isLoading) return <div className="text-center p-5"><CSpinner color="primary"/></div>
  
  if (!data || data.length === 0) {
    return <div className="text-center p-4 text-muted border rounded bg-light">Nenhum registo encontrado.</div>
  }

  return (
    <div className="border rounded overflow-hidden shadow-sm">
      <CTable hover responsive className="mb-0 align-middle">
        <CTableHead color="light">
          <CTableRow>
            {columns.map((col, index) => (
              <CTableHeaderCell key={index} scope="col">{col.label}</CTableHeaderCell>
            ))}
            {/* Coluna de Ações Condicional */}
            {actions && <CTableHeaderCell className="text-end" style={{width: '120px'}}>Ações</CTableHeaderCell>}
          </CTableRow>
        </CTableHead>
        <CTableBody>
          {data.map((item) => (
            <CTableRow key={item.id}>
              {columns.map((col, index) => (
                <CTableDataCell key={index}>
                  {/* Suporte para valores aninhados ou formatação customizada se necessário futuramente */}
                  {item[col.key]}
                </CTableDataCell>
              ))}
              
              {/* Botões de Ação */}
              {actions && (
                <CTableDataCell className="text-end">
                  <div className="d-flex justify-content-end gap-2">
                    {onEdit && (
                      <CTooltip content="Editar">
                        <CButton 
                          color="info" 
                          variant="ghost" 
                          size="sm"
                          onClick={() => onEdit(item)}
                        >
                          <CIcon icon={cilPencil} className="text-info" />
                        </CButton>
                      </CTooltip>
                    )}
                    
                    {onDelete && (
                      <CTooltip content="Apagar">
                        <CButton 
                          color="danger" 
                          variant="ghost" 
                          size="sm"
                          onClick={() => {
                            // "Bloqueio Rígido" começa aqui: Confirmação do utilizador
                            if(window.confirm('Tem a certeza absoluta? Esta ação não pode ser desfeita.')) {
                                onDelete(item.id)
                            }
                          }}
                        >
                          <CIcon icon={cilTrash} className="text-danger" />
                        </CButton>
                      </CTooltip>
                    )}
                  </div>
                </CTableDataCell>
              )}
            </CTableRow>
          ))}
        </CTableBody>
      </CTable>
    </div>
  )
}

export default SmartTable