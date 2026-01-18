import React, { useState, useMemo } from 'react'
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
  useSubjects,
  useCreateEntity, 
  useUpdateEntity, 
  useDeleteEntity 
} from '../hooks/useSchoolData'

const Courses = () => {
  const [modalVisible, setModalVisible] = useState(false)
  const [selectedItem, setSelectedItem] = useState(null)

  const { data: courses, isLoading } = useCourses()
  const { data: subjects } = useSubjects()
  const createMutation = useCreateEntity('courses')
  const updateMutation = useUpdateEntity('courses')
  const deleteMutation = useDeleteEntity('courses')
  
// Função auxiliar para formatar a lista de nomes (com truncagem se forem muitos)
  const formatList = (names) => {
    if (names.length === 0) return <span className="text-muted">-</span>;
    
    // Se tiver mais de 3 disciplinas, mostra "Matemática, Inglês, Português (+2)"
    if (names.length > 3) {
      const visible = names.slice(0, 3).join(', ');
      const remaining = names.length - 3;
      return <span title={names.join(', ')}>{visible} (+{remaining})</span>;
    }
    
    return names.join(', ');
  }

  const columns = [
    { key: 'name', label: 'Nome do Curso' },
    { 
      key: 'subjects', 
      label: 'Disciplinas',
      _style: { width: '50%' },
      // Agora que a SmartTable suporta render, isto vai funcionar!
      render: (item) => {
        // Lógica de visualização robusta (IDs ou Objetos)
        let ids = item.subject_ids || [];
        
        // Fallback: se vierem objetos em vez de IDs
        if (item.subjects && item.subjects.length > 0) {
            ids = item.subjects.map(s => s.id);
        }

        if (!subjects) return <span>...</span>;

        const names = ids.map(id => {
            const sub = subjects.find(s => s.id === id);
            return sub ? sub.name : null;
        }).filter(Boolean);

        return formatList(names);
      }
    }
    // REMOVIDA A COLUNA 'actions' MANUAL
  ]

  const handleCreate = () => {
    setSelectedItem(null)
    setModalVisible(true)
  }

  const handleEdit = (item) => {
    setSelectedItem(item)
    setModalVisible(true)
  }

  const handleDelete = async (id) => {
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
      <CRow className="mb-4 align-items-center">
        <CCol>
          <h2 className="mb-0 fw-bold text-dark">
            <CIcon icon={cilBookmark} className="me-2 text-primary" />
            Gestão de Cursos
          </h2>
          <small className="text-muted">Defina os cursos oferecidos pela escola e a sua estrutura curricular.</small>
        </CCol>
        <CCol className="text-end">
          <CButton color="primary" onClick={handleCreate} className="d-flex align-items-center gap-2 ms-auto">
            <CIcon icon={cilPlus} />
            Novo Curso
          </CButton>
        </CCol>
      </CRow>

      {deleteMutation.isError && (
        <CAlert color="danger" dismissible onClose={deleteMutation.reset}>
          <strong>Erro ao remover:</strong> {deleteMutation.error?.response?.data?.detail || "Ocorreu um erro."}
        </CAlert>
      )}

      <CCard className="border-0 shadow-sm">
        <CCardBody className="p-0">
          <SmartTable
            columns={columns}
            data={courses || []}
            isLoading={isLoading}
            actions={true}
            onEdit={handleEdit}
            onDelete={handleDelete}
          />
        </CCardBody>
      </CCard>

      <GenericModalForm
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
        title="Curso"
        initialData={selectedItem}
        FormComponent={CourseForm}
        onSubmit={handleFormSubmit}
        isLoading={activeMutation.isPending}
        error={activeMutation.error}
      />
    </div>
  )
}

export default Courses
