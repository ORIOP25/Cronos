import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { 
  CCard, CCardBody, CCol, CRow, CButton, CAlert, CBadge
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilBookmark, cilPlus } from '@coreui/icons'

import SmartTable from '../components/SmartTable'
import GenericModalForm from '../components/GenericModalForm'
import CourseForm from '../components/Forms/CourseForm'

import { 
  useCourses,
  useCreateEntity,
} from '../hooks/useSchoolData'

const Courses = () => {
  const navigate = useNavigate()
  const [modalVisible, setModalVisible] = useState(false)

  // 1. Hooks de Dados
  const { data: courses, isLoading } = useCourses()
  const createMutation = useCreateEntity('courses')

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
          {item.classes_count}
        </CBadge>
      )
    },
  ]

  // 3. Transformação de Dados (ViewModel)
  const tableData = (courses || []).map(c => ({
    ...c,
    classes_count: c.classes ? c.classes.length : 0,
  }))

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
      <CRow className="mb-4 align-items-center">
        <CCol>
          <h2 className="mb-0 fw-bold text-dark">
            <CIcon icon={cilBookmark} className="me-2 text-primary" />
            Gestão de Cursos
          </h2>
          <small className="text-muted">Crie cursos, defina o plano curricular e gere turmas iniciais.</small>
        </CCol>
        <CCol className="text-end">
          <CButton color="primary" onClick={handleCreate} className="d-flex align-items-center gap-2 ms-auto">
            <CIcon icon={cilPlus} />
            Novo Curso
          </CButton>
        </CCol>
      </CRow>

      {/* ERROS */}
      {createMutation.isError && (
        <CAlert color="danger" dismissible onClose={() => createMutation.reset()}>
          <strong>Erro:</strong>
          <div className="mt-1 text-sm">
            {(() => {
              const detail = createMutation.error?.response?.data?.detail;
              if (typeof detail === 'string') return detail;
              if (Array.isArray(detail)) {
                return (
                  <ul className="mb-0 ps-3">
                    {detail.map((err) => (
                      <li key={`${(err.loc || []).join('.')}-${err.msg}`}>
                        {err.msg} 
                        {err.loc ? <span className="opacity-75 ms-1">({err.loc.join(' -> ')})</span> : ''}
                      </li>
                    ))}
                  </ul>
                );
              }
              return createMutation.error?.message || "Ocorreu um erro inesperado.";
            })()}
          </div>
        </CAlert>
      )}

      {/* TABELA */}
      <CCard className="border-0 shadow-sm">
        <CCardBody className="p-0">
          <SmartTable
            columns={columns}
            data={tableData}
            isLoading={isLoading}
            onRowClick={handleRowClick}
          />
        </CCardBody>
      </CCard>

      {/* MODAL WIZARD (apenas criação — edição via CourseDetails) */}
      <GenericModalForm
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
        title="Novo Curso Profissional"
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
