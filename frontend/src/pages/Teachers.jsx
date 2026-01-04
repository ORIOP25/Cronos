import React, { useState } from 'react'
import { 
  CCard, CCardBody, CCol, CRow, CButton, CAlert, CBadge 
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilUserPlus, cilPeople } from '@coreui/icons'

// --- Arquitetura Limpa: Imports Padronizados ---
import SmartTable from '../components/SmartTable'
import GenericModalForm from '../components/GenericModalForm'
import TeacherForm from '../components/Forms/TeacherForm' // O formulário que acabámos de criar

// Hooks de Dados (Read & Write)
import { 
  useTeachers, 
  useCreateEntity, 
  useUpdateEntity, 
  useDeleteEntity 
} from '../hooks/useSchoolData'

const Teachers = () => {
  // 1. Gestão de Estado da Interface
  const [modalVisible, setModalVisible] = useState(false)
  const [selectedItem, setSelectedItem] = useState(null) // Se null = Criação, Se obj = Edição

  // 2. Hooks de Dados (A "Magia" acontece aqui)
  const { data: teachers, isLoading } = useTeachers()
  const createMutation = useCreateEntity('teachers')
  const updateMutation = useUpdateEntity('teachers')
  const deleteMutation = useDeleteEntity('teachers')

  // 3. Definição das Colunas da Tabela
  const columns = [
    { key: 'name', label: 'Nome' },
    { key: 'email', label: 'Email' },
    { key: 'login_status', label: 'Acesso' } // Campo calculado abaixo no map
  ]

  // 4. Preparação dos Dados para a Tabela (ViewModel)
  // Transformamos os dados brutos para adicionar badges visuais, etc.
  const tableData = (teachers || []).map(t => ({
    ...t,
    login_status: t.login_email ? (
      <CBadge color="success">Ativo</CBadge>
    ) : (
      <CBadge color="secondary">Sem Acesso</CBadge>
    )
  }))

  // --- Handlers (Controladores) ---

  const handleCreate = () => {
    setSelectedItem(null) // Modo Criação
    setModalVisible(true)
  }

  const handleEdit = (item) => {
    setSelectedItem(item) // Modo Edição
    setModalVisible(true)
  }

  const handleDelete = async (id) => {
    // A SmartTable já pediu confirmação (window.confirm)
    deleteMutation.mutate(id)
  }

  const handleFormSubmit = async (formData) => {
    if (selectedItem) {
      // UPDATE: Passamos ID e os dados novos
      await updateMutation.mutateAsync({ id: selectedItem.id, ...formData })
    } else {
      // CREATE: Apenas dados novos
      await createMutation.mutateAsync(formData)
    }
    // Se não houver erro (Async), fechamos o modal
    setModalVisible(false)
  }

  // Identificar qual mutação está ativa para mostrar loading/erros no modal
  const activeMutation = selectedItem ? updateMutation : createMutation

  return (
    <div className="p-4">
      {/* Cabeçalho da Página */}
      <CRow className="mb-4 align-items-center">
        <CCol>
          <h2 className="mb-0 fw-bold text-dark">
            <CIcon icon={cilPeople} className="me-2 text-primary" />
            Gestão de Professores
          </h2>
          <small className="text-muted">Gerir o corpo docente e acessos à plataforma.</small>
        </CCol>
        <CCol className="text-end">
          <CButton color="primary" onClick={handleCreate} className="d-flex align-items-center gap-2 ms-auto">
            <CIcon icon={cilUserPlus} />
            Novo Professor
          </CButton>
        </CCol>
      </CRow>

      {/* Tratamento de Erros Globais (ex: Erro ao Apagar) */}
      {deleteMutation.isError && (
        <CAlert color="danger" dismissible onClose={deleteMutation.reset}>
          <strong>Erro ao remover:</strong> {deleteMutation.error?.response?.data?.detail || "Ocorreu um erro."}
        </CAlert>
      )}

      {/* Tabela Inteligente */}
      <CCard className="border-0 shadow-sm">
        <CCardBody className="p-0">
          <SmartTable
            columns={columns}
            data={tableData}
            isLoading={isLoading}
            actions={true} // Ativa botões Editar/Apagar
            onEdit={handleEdit}
            onDelete={handleDelete}
          />
        </CCardBody>
      </CCard>

      {/* Modal Genérico (Reutilizável) */}
      <GenericModalForm
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
        title="Professor"
        initialData={selectedItem}
        FormComponent={TeacherForm} // Injetamos o formulário específico aqui
        onSubmit={handleFormSubmit}
        isLoading={activeMutation.isPending}
        error={activeMutation.error}
      />
    </div>
  )
}

export default Teachers