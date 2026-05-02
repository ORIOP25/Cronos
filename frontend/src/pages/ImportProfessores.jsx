import React, { useState } from 'react'
import apiClient from '../apiClient'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  CContainer, CNav, CNavItem, CNavLink, CTabContent, CTabPane, CCard, CCardBody, CRow, CCol, CButton
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { 
  cilUser, cilPeople, cilBook, cilRoom, cilClock, cilCloudUpload
} from '@coreui/icons'

// Importar componentes
import SimpleEntityForm from '../components/ImportForms/SimpleEntityForm'
import TimeslotImportForm from '../components/ImportForms/TimeslotImportForm'
import SmartTable from '../components/SmartTable'
import BulkImportModal from '../components/ImportForms/BulkImportModal'
import RoomImportForm from '../components/ImportForms/RoomImportForm'
import GlobalImportModal from '../components/ImportForms/GlobalImportModal' // <--- 1. IMPORTAÇÃO DO MODAL

// --- Funções API para criação (já existiam) ---
const apiCalls = {
  teacher: (data) => apiClient.post('/import/teacher', data).then(r => r.data),
  class:   (data) => apiClient.post('/import/class', data).then(r => r.data),
  subject: (data) => apiClient.post('/import/subject', data).then(r => r.data),
  room:    (data) => apiClient.post('/import/room', { ...data, type: 'normal' }).then(r => r.data),
}

// --- COMPONENTES GESTORES (Novo Padrão) ---

// 1. Gestor de Professores
const TeachersManager = () => {
  const queryClient = useQueryClient()
  const [showImportModal, setShowImportModal] = useState(false) // Estado do Modal

  const { data: list, isLoading } = useQuery({ queryKey: ['teachersList'], queryFn: async () => (await apiClient.get('/import/teachers')).data })
  
  const deleteMut = useMutation({ 
    mutationFn: (id) => apiClient.delete(`/import/teacher/${id}`), 
    onSuccess: () => queryClient.invalidateQueries(['teachersList']) 
  })

  // Função que o Modal vai usar para criar cada professor
  const processExcelRow = async (row) => {
    // Esperamos uma coluna 'name' no Excel
    if (!row.name) throw new Error("Coluna 'name' em falta")
    await apiClient.post('/import/teacher', { name: row.name })
  }

  return (
    <>
      <div className="d-flex justify-content-end mb-3">
        <CButton color="success" className="text-white" onClick={() => setShowImportModal(true)}>
          <CIcon icon={cilCloudUpload} className="me-2"/>
          Importar Excel
        </CButton>
      </div>

      <SimpleEntityForm 
        title="Adicionar Professor" 
        subtitle="Registe os docentes." 
        inputLabel="Nome" 
        mutationFn={apiCalls.teacher} 
        icon={cilUser} 
        onSuccessCallback={() => queryClient.invalidateQueries(['teachersList'])} 
      />
      
      <hr className="my-4"/>
      
      <SmartTable isLoading={isLoading} data={list} columns={[{ key: 'name', label: 'Nome' }]} onDelete={(id) => deleteMut.mutate(id)} />

      {/* O MODAL DE IMPORTAÇÃO */}
      <BulkImportModal 
        visible={showImportModal}
        onClose={() => {
            setShowImportModal(false)
            queryClient.invalidateQueries(['teachersList']) // Atualiza a lista ao fechar
        }}
        entityName="Professores"
        templateExample={{ name: "Prof. António" }}
        onProcessItem={processExcelRow}
      />
    </>
  )
}

// 2. Gestor de Turmas
const ClassesManager = () => {
  const queryClient = useQueryClient()
  const [showImportModal, setShowImportModal] = useState(false)

  const { data: list, isLoading } = useQuery({ queryKey: ['classesList'], queryFn: async () => (await apiClient.get('/import/classes')).data })
  
  const deleteMut = useMutation({ 
    mutationFn: (id) => apiClient.delete(`/import/class/${id}`), 
    onSuccess: () => queryClient.invalidateQueries(['classesList']) 
  })

  // Lógica para processar cada linha do Excel
  const processExcelRow = async (row) => {
    if (!row.name) throw new Error("Coluna 'name' em falta")
    await apiClient.post('/import/class', { name: row.name })
  }

  return (
    <>
      <div className="d-flex justify-content-end mb-3">
        <CButton color="success" className="text-white" onClick={() => setShowImportModal(true)}>
          <CIcon icon={cilCloudUpload} className="me-2"/>
          Importar Excel
        </CButton>
      </div>

      <SimpleEntityForm title="Adicionar Turma" subtitle="Crie as turmas." inputLabel="Nome (ex: 12º A)" mutationFn={apiCalls.class} icon={cilPeople} onSuccessCallback={() => queryClient.invalidateQueries(['classesList'])} />
      <hr className="my-4"/>
      <SmartTable isLoading={isLoading} data={list} columns={[{ key: 'name', label: 'Turma' }]} onDelete={(id) => deleteMut.mutate(id)} />

      <BulkImportModal 
        visible={showImportModal}
        onClose={() => { setShowImportModal(false); queryClient.invalidateQueries(['classesList']) }}
        entityName="Turmas"
        templateExample={{ name: "12º A" }}
        onProcessItem={processExcelRow}
      />
    </>
  )
}

// 3. Gestor de Disciplinas
const SubjectsManager = () => {
  const queryClient = useQueryClient()
  const [showImportModal, setShowImportModal] = useState(false)

  const { data: list, isLoading } = useQuery({ queryKey: ['subjectsList'], queryFn: async () => (await apiClient.get('/import/subjects')).data })
  
  const deleteMut = useMutation({ 
    mutationFn: (id) => apiClient.delete(`/import/subject/${id}`), 
    onSuccess: () => queryClient.invalidateQueries(['subjectsList']) 
  })

  const processExcelRow = async (row) => {
    if (!row.name) throw new Error("Coluna 'name' em falta")
    await apiClient.post('/import/subject', { name: row.name })
  }

  return (
    <>
      <div className="d-flex justify-content-end mb-3">
        <CButton color="success" className="text-white" onClick={() => setShowImportModal(true)}>
          <CIcon icon={cilCloudUpload} className="me-2"/>
          Importar Excel
        </CButton>
      </div>

      <SimpleEntityForm title="Adicionar Disciplina" subtitle="Defina o currículo." inputLabel="Nome (ex: Matemática)" mutationFn={apiCalls.subject} icon={cilBook} onSuccessCallback={() => queryClient.invalidateQueries(['subjectsList'])} />
      <hr className="my-4"/>
      <SmartTable isLoading={isLoading} data={list} columns={[{ key: 'name', label: 'Disciplina' }]} onDelete={(id) => deleteMut.mutate(id)} />

      <BulkImportModal 
        visible={showImportModal}
        onClose={() => { setShowImportModal(false); queryClient.invalidateQueries(['subjectsList']) }}
        entityName="Disciplinas"
        templateExample={{ name: "Matemática A" }}
        onProcessItem={processExcelRow}
      />
    </>
  )
}

// 4. Gestor de Salas (COM VALIDAÇÃO ESTRITA)
const RoomsManager = () => {
  const queryClient = useQueryClient()
  const [showImportModal, setShowImportModal] = useState(false)

  const { data: list, isLoading } = useQuery({ queryKey: ['roomsList'], queryFn: async () => (await apiClient.get('/import/rooms')).data })
  
  const deleteMut = useMutation({ 
    mutationFn: (id) => apiClient.delete(`/import/room/${id}`), 
    onSuccess: () => queryClient.invalidateQueries(['roomsList']) 
  })

  // --- 1. FUNÇÃO DE VALIDAÇÃO (O PORTEIRO) ---
  const validateRoomRow = (row) => {
    if (!row.name) return "Nome da sala em falta."
    
    // Normalizar para verificar
    const rawType = row.type ? String(row.type).toLowerCase().trim() : ''
    
    // Lista de valores aceites (Incluindo variações PT que convertemos para EN)
    // Se não estiver aqui, É ERRO.
    const validTerms = [
        'normal', 'sala de aula', 
        'lab', 'laboratorio', 'laboratório', 
        'gym', 'ginasio', 'ginásio', 'desporto'
    ]

    if (!rawType) return "Tipo de sala em falta (type)."
    if (!validTerms.includes(rawType)) {
        return `Tipo desconhecido: "${row.type}". Use 'normal', 'lab' ou 'gym'.`
    }
    return null // Null = Válido
  }

  // --- 2. PROCESSAMENTO (Só corre se passar a validação) ---
  const processExcelRow = async (row) => {
    // Aqui já sabemos que é válido, só precisamos de converter para o formato API
    let rawType = String(row.type).toLowerCase().trim()
    let finalType = 'normal'

    if (['lab', 'laboratorio', 'laboratório'].includes(rawType)) finalType = 'lab'
    else if (['gym', 'ginasio', 'ginásio', 'desporto'].includes(rawType)) finalType = 'gym'
    
    await apiClient.post('/import/room', { name: row.name, type: finalType })
  }

  return (
    <>
      <div className="d-flex justify-content-end mb-3">
        <CButton color="success" className="text-white" onClick={() => setShowImportModal(true)}>
          <CIcon icon={cilCloudUpload} className="me-2"/>
          Importar Excel
        </CButton>
      </div>

      <RoomImportForm onSuccessCallback={() => queryClient.invalidateQueries(['roomsList'])} />
      <hr className="my-4"/>
      <SmartTable isLoading={isLoading} data={list} columns={[{ key: 'name', label: 'Sala' }, { key: 'type', label: 'Tipo' }]} onDelete={(id) => deleteMut.mutate(id)} />

      <BulkImportModal 
        visible={showImportModal}
        onClose={() => { setShowImportModal(false); queryClient.invalidateQueries(['roomsList']) }}
        entityName="Salas"
        templateExample={{ name: "Laboratório 1", type: "lab" }} 
        // --- PASSAR O VALIDATOR ---
        validateRow={validateRoomRow}
        onProcessItem={processExcelRow}
      />
    </>
  )
}

// --- PÁGINA PRINCIPAL ---

const ImportWizard = () => {
  const [activeKey, setActiveKey] = useState(1)
  // 1. O ESTADO DO MODAL (Aberto ou Fechado?)
  const [showGlobalModal, setShowGlobalModal] = useState(false)
  // 2. O CLIENTE PARA ATUALIZAR DADOS
  const queryClient = useQueryClient()
  // Função para recarregar tudo depois de importar
  const refreshAllLists = () => {
      queryClient.invalidateQueries() 
  }

  return (
    <CContainer>
      <div className="d-flex justify-content-between align-items-center mb-4">
        <div>
          <h4 className="m-0 fw-bold">Configuração Escolar</h4>
          <p className="text-muted m-0 small">Defina os recursos e regras da sua escola.</p>
        </div>

        <div className="d-flex gap-2">
          <CButton color="dark" variant="outline" onClick={() => setShowGlobalModal(true)}>
            <CIcon icon={cilCloudUpload} className="me-2"/>
              Importação Global (Excel)
          </CButton>
        </div>
      </div>
      
      <CRow>
        <CCol xs={12}>
          <CCard className="shadow-sm border-0 mb-4">
            <CCardBody>
              <CNav variant="pills" layout="fill" role="tablist" className="p-1 bg-light rounded">
                <CNavItem><CNavLink active={activeKey === 1} onClick={() => setActiveKey(1)} style={{cursor: 'pointer', fontWeight: '500'}}><CIcon icon={cilUser} className="me-2"/>Professores</CNavLink></CNavItem>
                <CNavItem><CNavLink active={activeKey === 2} onClick={() => setActiveKey(2)} style={{cursor: 'pointer', fontWeight: '500'}}><CIcon icon={cilPeople} className="me-2"/>Turmas</CNavLink></CNavItem>
                <CNavItem><CNavLink active={activeKey === 3} onClick={() => setActiveKey(3)} style={{cursor: 'pointer', fontWeight: '500'}}><CIcon icon={cilBook} className="me-2"/>Disciplinas</CNavLink></CNavItem>
                <CNavItem><CNavLink active={activeKey === 4} onClick={() => setActiveKey(4)} style={{cursor: 'pointer', fontWeight: '500'}}><CIcon icon={cilRoom} className="me-2"/>Salas</CNavLink></CNavItem>
                <CNavItem><CNavLink active={activeKey === 5} onClick={() => setActiveKey(5)} style={{cursor: 'pointer', fontWeight: '500'}}><CIcon icon={cilClock} className="me-2"/>Horários</CNavLink></CNavItem>
              </CNav>
            </CCardBody>
          </CCard>

          <CTabContent>
            <CTabPane visible={activeKey === 1}><TeachersManager /></CTabPane>
            <CTabPane visible={activeKey === 2}><ClassesManager /></CTabPane>
            <CTabPane visible={activeKey === 3}><SubjectsManager /></CTabPane>
            <CTabPane visible={activeKey === 4}><RoomsManager /></CTabPane>
            
            <CTabPane visible={activeKey === 5}>
                {/* Nota: Timeslots ainda não têm Gestor (apenas form), podemos fazer no futuro */}
                <TimeslotImportForm />
            </CTabPane>
          </CTabContent>
        </CCol>
      </CRow>

      <GlobalImportModal 
        visible={showGlobalModal} 
        onClose={() => setShowGlobalModal(false)}
        onSuccess={refreshAllLists}
      />

    </CContainer>
  )
}

export default ImportWizard