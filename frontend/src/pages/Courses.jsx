import { useState } from 'react'
import PageHeader from '../components/PageHeader'
import { useNavigate } from 'react-router-dom'
import { CButton, CAlert, CBadge } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilPlus } from '@coreui/icons'

import SmartTable from '../components/SmartTable'
import GenericModalForm from '../components/GenericModalForm'
import CourseForm from '../components/Forms/CourseForm'
import { getApiErrorMessage } from '../utils/apiErrors'

import { 
  useCourses,
  useCreateCourse,
} from '../features/catalog/data'

const Courses = () => {
  const navigate = useNavigate()
  const [modalVisible, setModalVisible] = useState(false)

  // 1. Hooks de Dados
  const { data: courses, isLoading, isError, error, refetch } = useCourses()
  const createMutation = useCreateCourse()

  // 2. Colunas da Tabela
  const columns = [
    { key: 'name', label: 'Nome do Curso' },
    { key: 'abbreviation', label: 'Sigla' },
    {
      key: 'classes_count',
      label: 'Turmas',
      _style: { width: '12%' },
      render: (item) => (
        <CBadge color="success" shape="rounded-pill">
          {item.classes?.length ?? 0}
        </CBadge>
      )
    },
  ]

  // --- HANDLERS ---

  const handleCreate = () => {
    setModalVisible(true)
  }

  const handleRowClick = (item) => {
    navigate(`/courses/${item.id}`)
  }

  // Submissão do formulário (apenas criação — edição movida para CourseDetails)
  const handleFormSubmit = (formData) => {
    createMutation.mutate(formData, {
      onSuccess: () => setModalVisible(false)
    })
  }

  return (
    <div className="p-4">
      <PageHeader preTitle="Gestão" title="Cursos" />
      <div className="d-flex justify-content-end mb-4">
        <CButton color="primary" onClick={handleCreate} className="d-flex align-items-center gap-2">
          <CIcon icon={cilPlus} />
          Novo Curso
        </CButton>
      </div>

      {/* ERROS */}
      {createMutation.isError && (
        <CAlert color="danger" dismissible onClose={() => createMutation.reset()}>
          <strong>Erro:</strong>
          <div className="mt-1 text-sm">
            {getApiErrorMessage(createMutation.error)}
          </div>
        </CAlert>
      )}

      {/* TABELA */}
      <SmartTable
            columns={columns}
            data={courses || []}
            isLoading={isLoading}
            isError={isError}
            error={error}
            onRetry={() => refetch()}
            onRowClick={handleRowClick}
            getRowLabel={(course) => course.name}
          />

      {/* MODAL WIZARD (apenas criação — edição via CourseDetails) */}
      <GenericModalForm
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
        title="Curso Profissional"
        size="lg"
        FormComponent={CourseForm}
        onSubmit={handleFormSubmit}
        isLoading={createMutation.isPending}
        error={createMutation.error}
      />
    </div>
  )
}

export default Courses
