import { useState } from 'react'
import PageHeader from '../components/PageHeader'
import { useNavigate } from 'react-router-dom'
import { toast } from 'react-hot-toast'
import { CButton, CBadge } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilPlus } from '@coreui/icons'

import SmartTable from '../components/SmartTable'
import GenericModalForm from '../components/GenericModalForm'
import CourseForm from '../components/Forms/CourseForm'
import { getApiErrorMessage } from '../utils/apiErrors'
import { useAttemptScope } from '../hooks/useAttemptScope'

import { 
  useCourses,
  useCreateCourse,
  useDeleteCourse,
} from '../features/catalog/data'

const Courses = () => {
  const navigate = useNavigate()
  const [modalVisible, setModalVisible] = useState(false)

  // 1. Hooks de Dados
  const { data: courses, isLoading, isError, error, refetch } = useCourses()
  const createMutation = useCreateCourse()
  const deleteMutation = useDeleteCourse()
  const attemptScope = useAttemptScope()

  // 2. Colunas da Tabela
  const columns = [
    { key: 'name', label: 'Nome do curso' },
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
    createMutation.mutate(formData, attemptScope.guard({
      onSuccess: () => {
        setModalVisible(false)
        toast.success('Curso criado.')
      },
      onError: (error) => toast.error(getApiErrorMessage(error, 'Não foi possível criar o curso. Tente novamente.')),
    }))
  }

  return (
    <div className="p-4">
      <PageHeader preTitle="Gestão" title="Cursos">
        <CButton color="secondary" variant="outline" onClick={() => navigate('/imports?resource=courses')}>Importar CSV</CButton>
        <CButton color="primary" onClick={handleCreate} className="d-flex align-items-center gap-2" data-tutorial-target="new-course">
          <CIcon icon={cilPlus} />
          Novo curso
        </CButton>
      </PageHeader>

      {/* TABELA */}
      <SmartTable
            columns={columns}
            data={courses || []}
            isLoading={isLoading}
            isError={isError}
            error={error}
            onRetry={() => refetch()}
            onDelete={(id) => deleteMutation.mutateAsync(id)}
            deleteMessage="As associações de configuração serão retiradas e o histórico preservado. Remova primeiro as turmas atuais."
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
        tutorialTarget="course-form"
      />
    </div>
  )
}

export default Courses
