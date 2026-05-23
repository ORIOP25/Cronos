import React, { useState } from 'react'
import PageHeader from '../components/PageHeader'
import {
  CCard, CCardBody, CButton, CAlert, CBadge 
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilPlus } from '@coreui/icons'

import SmartTable from '../components/SmartTable'
import GenericModalForm from '../components/GenericModalForm'
import ClassForm from '../components/Forms/ClassForm'

// Hooks de Dados (CRUD)
import { 
  useClasses,
  useCourses,
  useCreateEntity, 
  useUpdateEntity, 
  useDeleteEntity 
} from '../hooks/useSchoolData'

const Classes = () => {
  const [modalVisible, setModalVisible] = useState(false)
  const [selectedItem, setSelectedItem] = useState(null)

  // 1. Acesso aos Dados
  const { data: classes, isLoading, isError, error, refetch } = useClasses()
  const { data: courses } = useCourses()
  const createMutation = useCreateEntity('classes')
  const updateMutation = useUpdateEntity('classes')
  const deleteMutation = useDeleteEntity('classes')

  // 2. Definição das Colunas
  const columns = [
    { key: 'name', label: 'Turma' },
    { key: 'size_badge', label: 'Nº Alunos' },
    { key: 'course_badge', label: 'Curso' }
  ]

  // 3. Transformação (ViewModel)
  const tableData = (classes || []).map(c => {
    // Procura o nome do curso pelo ID
    const courseName = courses?.find(course => course.id === c.course_id)?.name
    
    return {
      ...c,
      size_badge: <CBadge color="info" shape="rounded-pill">{c.size} alunos</CBadge>,
      course_badge: c.course_id ? (
        <CBadge color="success" shape="rounded-pill">{courseName || 'Carregando...'}</CBadge>
      ) : (
        <CBadge color="secondary" shape="rounded-pill">Sem curso</CBadge>
      )
    }
  })

  // --- Handlers ---

  const handleCreate = () => {
    setSelectedItem(null)
    setModalVisible(true)
  }

  const handleEdit = (item) => {
    setSelectedItem(item)
    setModalVisible(true)
  }

  const handleDelete = (id) => {
    deleteMutation.mutate(id)
  }

  const handleFormSubmit = async (formData) => {
    if (selectedItem) {
      await updateMutation.mutateAsync({ id: selectedItem.id, ...formData })
    } else {
      await createMutation.mutateAsync(formData)
    }
    setModalVisible(false)
  }

  const activeMutation = selectedItem ? updateMutation : createMutation

  return (
    <div className="p-4">
      <PageHeader preTitle="Gestão" title="Turmas" />
      <div className="d-flex justify-content-end mb-4">
        <CButton color="primary" onClick={handleCreate} className="d-flex align-items-center gap-2">
          <CIcon icon={cilPlus} />
          Nova Turma
        </CButton>
      </div>

      {/* Tratamento de Erros de Eliminação */}
      {deleteMutation.isError && (
        <CAlert color="danger" dismissible onClose={deleteMutation.reset}>
          <strong>Erro ao remover:</strong> {
            (() => {
              const detail = deleteMutation.error?.response?.data?.detail;
              if (Array.isArray(detail)) {
                 return detail.map(e => e.msg).join(', ');
              }
              return detail || "Ocorreu um erro desconhecido.";
            })()
          }
        </CAlert>
      )}

      <CCard className="border-0 shadow-sm">
        <CCardBody className="p-0">
          <SmartTable
            columns={columns}
            data={tableData}
            isLoading={isLoading}
            isError={isError}
            error={error}
            onRetry={() => refetch()}
            actions={true}
            onEdit={handleEdit}
            onDelete={handleDelete}
          />
        </CCardBody>
      </CCard>

      <GenericModalForm
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
        title="Turma"
        initialData={selectedItem}
        FormComponent={ClassForm}
        onSubmit={handleFormSubmit}
        isLoading={activeMutation.isPending}
        error={activeMutation.error}
      />
    </div>
  )
}

export default Classes