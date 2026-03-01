import React, { useState, useRef } from 'react'
import * as XLSX from 'xlsx'
import apiClient from '../../apiClient'
import PropTypes from 'prop-types'
import { 
  CModal, CModalHeader, CModalTitle, CModalBody, CModalFooter, 
  CButton, CFormInput, CProgress, CAlert, CTable, CTableHead, CTableRow, CTableHeaderCell, CTableBody, CTableDataCell, CBadge
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilFile, cilCloudUpload, cilBan, cilCheckCircle } from '@coreui/icons'

const GlobalImportModal = ({ visible, onClose, onSuccess }) => {
  const fileInputRef = useRef()
  const [processing, setProcessing] = useState(false)
  const [progress, setProgress] = useState(0)
  
  // Estados de Validação
  const [errors, setErrors] = useState([]) // Lista de erros encontrados
  const [preparedData, setPreparedData] = useState(null) // Dados prontos a enviar se não houver erros
  const [stats, setStats] = useState(null) // Contagens para mostrar resumo

  const handleFileUpload = (e) => {
    const file = e.target.files[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (evt) => {
      const bstr = evt.target.result
      const wb = XLSX.read(bstr, { type: 'binary' })
      const wsname = wb.SheetNames[0] // Lê apenas a primeira folha
      const ws = wb.Sheets[wsname]
      const data = XLSX.utils.sheet_to_json(ws)
      
      validateAndParse(data)
    }
    reader.readAsBinaryString(file)
  }

  // --- LÓGICA DE VALIDAÇÃO ESTRITA ---
  const validateAndParse = (rows) => {
    const newErrors = []
    const cleanData = {
      teachers: [],
      classes: [],
      subjects: [],
      rooms: []
    }

    // Tipos de sala permitidos (ESTRITO)
    const ALLOWED_ROOM_TYPES = new Set(['normal', 'lab', 'gym'])

    rows.forEach((row, index) => {
      const rowNum = index + 2 // Excel começa na linha 1 + cabeçalho

      // 1. Validar e Extrair PROFESSORES
      if (row.teacher) {
        cleanData.teachers.push({ name: String(row.teacher).trim() })
      }

      // 2. Validar e Extrair TURMAS
      if (row.class) {
        cleanData.classes.push({ name: String(row.class).trim() })
      }

      // 3. Validar e Extrair DISCIPLINAS
      if (row.subject) {
        cleanData.subjects.push({ name: String(row.subject).trim() })
      }

      // 4. Validar e Extrair SALAS (A parte crítica)
      if (row.room) {
        const rName = String(row.room).trim()
        const rType = row.room_type ? String(row.room_type).trim() : null

        if (!rType) {
          newErrors.push({ 
            row: rowNum, 
            col: 'room_type', 
            msg: `A sala "${rName}" não tem tipo definido.` 
          })
        } else if (!ALLOWED_ROOM_TYPES.has(rType)) {
          newErrors.push({ 
            row: rowNum, 
            col: 'room_type', 
            msg: `Tipo "${rType}" inválido. Use apenas: normal, lab, gym.` 
          })
        } else {
          // Só adiciona se for válido
          cleanData.rooms.push({ name: rName, type: rType })
        }
      } else if (row.room_type) {
        // Se tem tipo mas não tem nome
        newErrors.push({ row: rowNum, col: 'room', msg: 'Definiu um tipo de sala sem nome da sala.' })
      }
    })

    setErrors(newErrors)
    
    if (newErrors.length === 0) {
      setPreparedData(cleanData)
      setStats({
        teachers: cleanData.teachers.length,
        classes: cleanData.classes.length,
        subjects: cleanData.subjects.length,
        rooms: cleanData.rooms.length,
        total: cleanData.teachers.length + cleanData.classes.length + cleanData.subjects.length + cleanData.rooms.length
      })
    } else {
      setPreparedData(null)
      setStats(null)
    }
  }

  // --- ENVIO PARA A API ---
  const handleImport = async () => {
    if (!preparedData) return

    setProcessing(true)
    setProgress(0)
    
    const totalItems = stats.total
    let currentItem = 0

    const updateProgress = () => {
      currentItem++
      setProgress(Math.round((currentItem / totalItems) * 100))
    }

    try {
      // Enviar Professores
      for (const item of preparedData.teachers) {
        try { await apiClient.post('/import/teacher', item); } catch(e){}
        updateProgress()
      }
      // Enviar Turmas
      for (const item of preparedData.classes) {
        try { await apiClient.post('/import/class', item); } catch(e){}
        updateProgress()
      }
      // Enviar Disciplinas
      for (const item of preparedData.subjects) {
        try { await apiClient.post('/import/subject', item); } catch(e){}
        updateProgress()
      }
      // Enviar Salas
      for (const item of preparedData.rooms) {
        try { await apiClient.post('/import/room', item); } catch(e){}
        updateProgress()
      }

      alert("Importação concluída com sucesso!")
      if (onSuccess) onSuccess()
      handleClose()

    } catch (err) {
      console.error(err)
      alert("Ocorreu um erro inesperado durante a importação.")
    } finally {
      setProcessing(false)
    }
  }

  const handleClose = () => {
    setErrors([])
    setPreparedData(null)
    setStats(null)
    setProgress(0)
    if (fileInputRef.current) fileInputRef.current.value = ""
    onClose()
  }

  return (
    <CModal visible={visible} onClose={handleClose} size="lg" backdrop="static">
      <CModalHeader onClose={handleClose}>
        <CModalTitle>Importação Global (Ficheiro Único)</CModalTitle>
      </CModalHeader>
      <CModalBody>
        
        {/* FASE 1: UPLOAD */}
        {!processing && !preparedData && errors.length === 0 && (
            <div className="mb-4">
                <CAlert color="info">
                    <strong>Regras:</strong> Carregue um único ficheiro Excel (.xlsx) com as colunas em Inglês:
                    <br/>
                    <code>teacher</code>, <code>class</code>, <code>subject</code>, <code>room</code>, <code>room_type</code>
                    <br/>
                    <small>Nota: <strong>room_type</strong> tem de ser estrito: <em>normal, lab, gym</em>.</small>
                </CAlert>
                
                <div className="p-5 border rounded bg-light text-center" style={{borderStyle: 'dashed !important'}}>
                    <CIcon icon={cilFile} size="4xl" className="text-secondary mb-3"/>
                    <h5>Selecione o ficheiro Excel</h5>
                    <CFormInput type="file" accept=".xlsx, .xls, .csv" ref={fileInputRef} onChange={handleFileUpload} className="mt-3 w-75 mx-auto"/>
                </div>
            </div>
        )}

        {/* FASE 2: ERROS ENCONTRADOS (Só mostra se houver erros) */}
        {errors.length > 0 && (
            <div>
                <div className="d-flex align-items-center mb-3 text-danger">
                    <CIcon icon={cilBan} size="xl" className="me-2"/>
                    <h5 className="m-0">Foram encontrados erros</h5>
                </div>
                <p className="text-muted small">Corrija o ficheiro Excel e tente novamente. A importação está bloqueada.</p>
                
                <div style={{maxHeight: '300px', overflowY: 'auto'}} className="border rounded">
                    <CTable hover small className="mb-0">
                        <CTableHead color="danger">
                            <CTableRow>
                                <CTableHeaderCell>Linha Excel</CTableHeaderCell>
                                <CTableHeaderCell>Coluna</CTableHeaderCell>
                                <CTableHeaderCell>Erro</CTableHeaderCell>
                            </CTableRow>
                        </CTableHead>
                        <CTableBody>
                            {errors.map((err) => (
                                <CTableRow key={`${err.row}-${err.col}`}>
                                    <CTableDataCell>#{err.row}</CTableDataCell>
                                    <CTableDataCell className="fw-bold">{err.col}</CTableDataCell>
                                    <CTableDataCell className="text-danger">{err.msg}</CTableDataCell>
                                </CTableRow>
                            ))}
                        </CTableBody>
                    </CTable>
                </div>
            </div>
        )}

        {/* FASE 3: RESUMO E CONFIRMAÇÃO (Só mostra se estiver tudo OK) */}
        {preparedData && !processing && (
            <div className="text-center py-4">
                <CIcon icon={cilCheckCircle} size="4xl" className="text-success mb-3"/>
                <h4>Tudo pronto para importar!</h4>
                <p className="text-muted">O ficheiro foi validado com sucesso.</p>
                
                <div className="d-flex justify-content-center gap-3 mt-4">
                    <CBadge color="primary" shape="rounded-pill" className="p-2 px-3 fs-6">
                        {stats.teachers} Professores
                    </CBadge>
                    <CBadge color="info" shape="rounded-pill" className="p-2 px-3 fs-6">
                        {stats.classes} Turmas
                    </CBadge>
                    <CBadge color="warning" shape="rounded-pill" className="p-2 px-3 fs-6 text-dark">
                        {stats.subjects} Disciplinas
                    </CBadge>
                    <CBadge color="secondary" shape="rounded-pill" className="p-2 px-3 fs-6">
                        {stats.rooms} Salas
                    </CBadge>
                </div>
            </div>
        )}

        {/* FASE 4: A PROCESSAR */}
        {processing && (
            <div className="py-4 text-center">
                <h5 className="mb-3">A importar para a base de dados...</h5>
                <CProgress className="mb-3" height={20} value={progress} color="success" variant="striped" animated>
                    {progress}%
                </CProgress>
            </div>
        )}

      </CModalBody>
      <CModalFooter>
        <CButton color="secondary" onClick={handleClose} disabled={processing}>
          {errors.length > 0 ? 'Fechar e Corrigir' : 'Cancelar'}
        </CButton>
        
        {/* Botão Importar só aparece se houver dados preparados e zero erros */}
        {preparedData && !processing && (
          <CButton color="success" className="text-white" onClick={handleImport}>
            <CIcon icon={cilCloudUpload} className="me-2"/>
            Confirmar e Importar
          </CButton>
        )}
      </CModalFooter>
    </CModal>
  )
}

export default GlobalImportModal

GlobalImportModal.propTypes = {
  visible: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  onSuccess: PropTypes.func,
}