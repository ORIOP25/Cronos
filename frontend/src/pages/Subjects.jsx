import React, { useState } from 'react'
import { 
  CCard, CCardBody, CCol, CRow, CButton, CAlert, CBadge 
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilBook, cilPlus } from '@coreui/icons'

import SmartTable from '../components/SmartTable'
import GenericModalForm from '../components/GenericModalForm'
import SubjectForm from '../components/Forms/SubjectForm'

// Hooks de Dados
import { 
  useSubjects, 
  useCreateEntity, 
  useUpdateEntity, 
  useDeleteEntity 
} from '../hooks/useSchoolData'

const Subjects = () => {
  const [modalVisible, setModalVisible] = useState(false)
  const [selectedItem, setSelectedItem] = useState(null)

  // 1. Acesso aos Dados
  const { data: subjects, isLoading } = useSubjects()
  const createMutation = useCreateEntity('subjects')
  const updateMutation = useUpdateEntity('subjects')
  const deleteMutation = useDeleteEntity('subjects')

  // 2. Definição das Colunas
  const columns = [
    { key: 'name', label: 'Disciplina' },
    { key: 'room_badge', label: 'Requisito de Sala' }
  ]

  // 3. Transformação (ViewModel)
  const tableData = (subjects || []).map(s => ({
    ...s,
    room_badge: getRoomBadge(s.required_room_type)
  }))

  function getRoomBadge(type) {
    switch (type) {
      case 'gym': return <CBadge color="warning" shape="rounded-pill">Ginásio</CBadge>
      case 'lab': return <CBadge color="info" shape="rounded-pill">Laboratório</CBadge>
      case 'art': return <CBadge color="danger" shape="rounded-pill">Artes</CBadge>
      default: return <CBadge color="light" className="text-dark">Sala Normal</CBadge>
    }
  }

  // --- Handlers ---

  const handleCreate = () => {
    // Wizard: Sempre começa do zero (Opção A - Decisão Arquitetural)
    setSelectedItem(null)
    setModalVisible(true)
  }

  const handleEdit = (item) => {
    // RESTRIÇÃO: Por enquanto, edição simples (Fase 6)
    // O Wizard é apenas para CRIAÇÃO (Opção A)
    setSelectedItem(item)
    setModalVisible(true)
  }

  const handleDelete = (id) => {
    deleteMutation.mutate(id)
  }

  const handleFormSubmit = (formData) => {
    if (selectedItem) {
      // --- MODO EDIÇÃO (Stability) ---
      // Usa PUT/PATCH e envia o ID
      updateMutation.mutate(
        { id: selectedItem.id, ...formData },
        { onSuccess: () => setModalVisible(false) }
      )
    } else {
      // --- MODO CRIAÇÃO ---
      // Usa POST
      createMutation.mutate(formData, {
        onSuccess: () => setModalVisible(false)
      })
    }
  }

  const activeMutation = selectedItem ? updateMutation : createMutation

  return (
    <div className="p-4">
      <CRow className="mb-4 align-items-center">
        <CCol>
          <h2 className="mb-0 fw-bold text-dark">
            <CIcon icon={cilBook} className="me-2 text-info" />
            Gestão de Disciplinas
          </h2>
          <small className="text-muted">Defina as unidades curriculares, tipos de sala e módulos associados.</small>
        </CCol>
        <CCol className="text-end">
          <CButton color="primary" onClick={handleCreate} className="d-flex align-items-center gap-2 ms-auto">
            <CIcon icon={cilPlus} />
            Nova Disciplina
          </CButton>
        </CCol>
      </CRow>

      {/* Tratamento de Erros de Criação/Eliminação */}
      {createMutation.isError && (
        <CAlert color="danger" dismissible onClose={createMutation.reset}>
          <strong>Erro ao criar:</strong> {createMutation.error?.response?.data?.detail || "Erro desconhecido."}
        </CAlert>
      )}

      {deleteMutation.isError && (
        <CAlert color="danger" dismissible onClose={deleteMutation.reset}>
          <strong>Erro ao remover:</strong> {deleteMutation.error?.response?.data?.detail || "Erro de dependência."}
        </CAlert>
      )}

      <CCard className="border-0 shadow-sm">
        <CCardBody className="p-0">
          <SmartTable
            columns={columns}
            data={tableData}
            isLoading={isLoading}
            actions={true}
            onEdit={handleEdit}
            onDelete={handleDelete}
          />
        </CCardBody>
      </CCard>

      {/* MODAL COM WIZARD (Opção A: Criação com módulos) */}
      <GenericModalForm
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
        title={selectedItem ? "Editar Disciplina" : "Nova Disciplina (Wizard)"}
        initialData={selectedItem}
        FormComponent={SubjectForm}
        onSubmit={handleFormSubmit}
        isLoading={activeMutation.isPending}
        error={activeMutation.error}
      />
    </div>
  )
}

export default Subjects