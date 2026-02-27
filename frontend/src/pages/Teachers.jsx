import React, { useState } from 'react'
import { 
  CCard, CCardBody, CCol, CRow, CButton, CAlert
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilUserPlus, cilPeople, cilUser } from '@coreui/icons'

// --- Arquitetura Limpa: Imports Padronizados ---
import SmartTable from '../components/SmartTable'
import GenericModalForm from '../components/GenericModalForm'
import TeacherForm from '../components/Forms/TeacherForm' // O formulário que acabámos de criar

// Hooks de Dados (Read & Write)
import { 
  useTeachers,
  useSubjects, 
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
  const { data: subjects } = useSubjects()
  const createMutation = useCreateEntity('teachers')
  const updateMutation = useUpdateEntity('teachers')
  const deleteMutation = useDeleteEntity('teachers')

  // Função auxiliar para formatar listas (igual à de Courses)
  const formatList = (names) => {
    if (!names.length) return <span className="text-muted">-</span>;
    if (names.length > 3) {
      return <span title={names.join(', ')}>{names.slice(0, 3).join(', ')} (+{names.length - 3})</span>;
    }
    return names.join(', ');
  }

  // 3. Definição das Colunas da Tabela
  const columns = [
    { key: 'name', label: 'Nome' },
    { 
        key: 'email', 
        label: 'Email / Acesso',
        render: (item) => (
            <div>
                {/* Mostrar email (agora persiste mesmo se inativo) */}
                <div className="fw-bold">{item.email || '-'}</div>
                
                {/* Lógica Visual: Ativo vs Inativo */}
                {item.email && (
                    item.is_active ? (
                        <small className="text-success d-flex align-items-center mt-1">
                            <CIcon icon={cilUser} size="sm" className="me-1"/>
                            <span>Conta Ativa</span>
                        </small>
                    ) : (
                        <small className="text-muted d-flex align-items-center mt-1">
                            <CIcon icon={cilUser} size="sm" className="me-1"/>
                            <span>Inativo</span>
                        </small>
                    )
                )}
            </div>
        )
    },
    { 
        key: 'subjects', 
        label: 'Competências', 
        _style: { width: '40%' },
        render: (item) => {
            // 1. Resiliência: Obter IDs venham eles como venham
            let ids = item.subject_ids || [];
            if (item.subjects && item.subjects.length > 0) {
                ids = item.subjects.map(s => s.id);
            }

            // 2. Loading State: Se ainda não temos disciplinas, mostramos "..."
            if (!subjects) return <span className="text-muted">...</span>;

            // 3. Tradução: ID -> Nome
            const names = ids.map(id => {
                const sub = subjects.find(s => s.id === id);
                return sub ? sub.name : null;
            }).filter(Boolean); // Remove nulos

            // 4. Formatação bonita
            return formatList(names);
        }
    },
  ]

  // 4. Preparação dos Dados para a Tabela (ViewModel)
  const tableData = teachers || []

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