import React, { useState, useRef } from 'react'
import * as XLSX from 'xlsx'
import { 
  CModal, CModalHeader, CModalTitle, CModalBody, CModalFooter, 
  CButton, CFormInput, CProgress, CAlert, CTable, CTableHead, CTableRow, CTableHeaderCell, CTableBody, CTableDataCell, CBadge, CTooltip
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilCloudUpload, cilBan } from '@coreui/icons'

const BulkImportModal = ({ visible, onClose, entityName, onProcessItem, templateExample, validateRow }) => {
  const fileInputRef = useRef()
  const [fileData, setFileData] = useState([])
  const [processing, setProcessing] = useState(false)
  const [progress, setProgress] = useState(0)
  const [logs, setLogs] = useState([])
  const [hasValidationErrors, setHasValidationErrors] = useState(false)

  // 1. LER O FICHEIRO EXCEL E VALIDAR
  const handleFileUpload = (e) => {
    const file = e.target.files[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (evt) => {
      const bstr = evt.target.result
      const wb = XLSX.read(bstr, { type: 'binary' })
      const wsname = wb.SheetNames[0]
      const ws = wb.Sheets[wsname]
      const rawData = XLSX.utils.sheet_to_json(ws)
      
      // --- VALIDAÇÃO PRÉVIA ---
      let errorFound = false
      const validatedData = rawData.map(row => {
        let error = null
        if (validateRow) {
            error = validateRow(row) // Retorna string de erro ou null
        }
        if (error) errorFound = true
        return { ...row, _error: error } // Adiciona o erro ao objeto para mostrar na tabela
      })

      setFileData(validatedData)
      setHasValidationErrors(errorFound)
      setLogs([])
      setProgress(0)
    }
    reader.readAsBinaryString(file)
  }

  // 2. PROCESSAR DADOS
  const handleImport = async () => {
    if (hasValidationErrors) return // Bloqueio extra

    setProcessing(true)
    setLogs([])
    let successCount = 0
    let errorCount = 0

    for (let i = 0; i < fileData.length; i++) {
      // Removemos a prop interna '_error' antes de enviar para a API
      const { _error, ...row } = fileData[i]
      
      try {
        await onProcessItem(row)
        successCount++
      } catch (err) {
        console.error(err)
        errorCount++
        setLogs(prev => [...prev, { row: i + 1, error: "Falha na API" }])
      }
      setProgress(Math.round(((i + 1) / fileData.length) * 100))
    }

    setProcessing(false)
    if (errorCount === 0) {
      alert(`Sucesso! ${successCount} registos importados.`)
      handleClose()
    } else {
      alert(`Concluído com avisos. ${successCount} sucessos, ${errorCount} erros.`)
    }
  }

  const handleClose = () => {
    setFileData([])
    setProgress(0)
    setLogs([])
    setHasValidationErrors(false)
    if (fileInputRef.current) fileInputRef.current.value = ""
    onClose()
  }

  return (
    <CModal visible={visible} onClose={handleClose} size="xl" backdrop="static">
      <CModalHeader onClose={handleClose}>
        <CModalTitle>Importar {entityName} em Massa</CModalTitle>
      </CModalHeader>
      
      <CModalBody>
        {!processing && progress === 0 && (
          <>
            <div className="mb-4 p-3 bg-light border rounded">
              <h6>Instruções:</h6>
              <p className="small text-muted mb-2">
                O ficheiro deve ter as colunas corretas.
                <br/>Exemplo válido:
              </p>
              <code className="d-block bg-white p-2 border rounded mb-3">
                {JSON.stringify([templateExample], null, 2)}
              </code>
              
              <CFormInput type="file" accept=".xlsx, .xls, .csv" ref={fileInputRef} onChange={handleFileUpload} />
            </div>

            {/* AVISO DE ERROS */}
            {hasValidationErrors && (
                <CAlert color="danger" className="d-flex align-items-center">
                    <CIcon icon={cilBan} className="me-2"/>
                    <div>
                        <strong>Atenção:</strong> O ficheiro contém dados inválidos. 
                        Corrija as linhas marcadas a vermelho no Excel e carregue novamente.
                    </div>
                </CAlert>
            )}

            {/* PRÉ-VISUALIZAÇÃO INTELIGENTE (CORRIGIDA) */}
            {fileData.length > 0 && (
              <div>
                <h6>Pré-visualização e Validação ({fileData.length} registos):</h6>
                <div style={{maxHeight: '400px', overflowY: 'auto'}}>
                  <CTable small bordered hover>
                    <CTableHead color="light">
                      <CTableRow>
                        {/* 1. Definimos as colunas com base na primeira linha (para garantir ordem) */}
                        {Object.keys(fileData[0])
                            .filter(k => k !== '_error')
                            .map((key) => (
                                <CTableHeaderCell key={key}>{key}</CTableHeaderCell>
                            ))
                        }
                        <CTableHeaderCell>Estado</CTableHeaderCell>
                      </CTableRow>
                    </CTableHead>
                    <CTableBody>
                      {fileData.map((row, idx) => {
                        // 2. Recuperamos as chaves da primeira linha para manter o alinhamento
                        // (Mesmo que esta linha específica não tenha esse dado)
                        const columns = Object.keys(fileData[0]).filter(k => k !== '_error');
                        
                        return (
                            <CTableRow key={idx} color={row._error ? 'danger' : ''}>
                              {columns.map((colKey, i) => (
                                  <CTableDataCell key={i}>
                                    {/* Se o dado não existir (undefined), mostramos vazio ou traço */}
                                    {row[colKey] || <span className="text-muted">-</span>}
                                  </CTableDataCell>
                              ))}
                              
                              {/* A Coluna de Estado fica sempre no fim, alinhada */}
                              <CTableDataCell>
                                  {row._error ? (
                                      <CTooltip content={row._error}>
                                          <CBadge color="danger" style={{cursor: 'help'}}>Inválido</CBadge>
                                      </CTooltip>
                                  ) : (
                                      <CBadge color="success">OK</CBadge>
                                  )}
                              </CTableDataCell>
                            </CTableRow>
                        )
                      })}
                    </CTableBody>
                  </CTable>
                </div>
              </div>
            )}
          </>
        )}

        {(processing || progress > 0) && (
          <div className="text-center py-4">
            <h5 className="mb-3">{processing ? 'A importar dados...' : 'Concluído!'}</h5>
            <CProgress className="mb-3" height={20} value={progress} color="success" variant="striped" animated={processing}>
              {progress}%
            </CProgress>
          </div>
        )}

      </CModalBody>
      <CModalFooter>
        <CButton color="secondary" onClick={handleClose} disabled={processing}>
          Cancelar
        </CButton>
        {fileData.length > 0 && progress === 0 && (
          <CButton 
            color="primary" 
            onClick={handleImport} 
            disabled={hasValidationErrors} // BLOQUEIA SE HOUVER ERROS
          >
            <CIcon icon={cilCloudUpload} className="me-2"/>
            {hasValidationErrors ? 'Corrija os erros' : 'Iniciar Importação'}
          </CButton>
        )}
      </CModalFooter>
    </CModal>
  )
}

export default BulkImportModal