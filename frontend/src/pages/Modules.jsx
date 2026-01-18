import React, { useState, useMemo } from 'react'
import { 
  CCard, CCardBody, CCol, CRow, CButton, CAlert, CFormSelect
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilList, cilPlus } from '@coreui/icons'

import SmartTable from '../components/SmartTable'
import GenericModalForm from '../components/GenericModalForm'
import ModuleForm from '../components/Forms/ModuleForm'

import { 
  useModules,
  useSubjects,
  useCreateEntity, 
  useUpdateEntity, 
  useDeleteEntity 
} from '../hooks/useSchoolData'

const Modules = () => {
  const [modalVisible, setModalVisible] = useState(false)
  const [selectedItem, setSelectedItem] = useState(null)
  const [filterSubjectId, setFilterSubjectId] = useState('') // Filtro por disciplina

  const { data: modules, isLoading } = useModules()
  const { data: subjects } = useSubjects()
  const createMutation = useCreateEntity('modules')
  const updateMutation = useUpdateEntity('modules')
  const deleteMutation = useDeleteEntity('modules')

  // --- Filtro por Disciplina ---
  const filteredModules = useMemo(() => {
    if (!modules) return []
    if (!filterSubjectId) return modules
    return modules.filter(m => m.subject_id === parseInt(filterSubjectId))
  }, [modules, filterSubjectId])

  // --- Mapeamento de subject_id para nome (para a tabela) ---
  const subjectMap = useMemo(() => {
    const map = {}
    if (subjects) {
      subjects.forEach(s => {
        map[s.id] = s.name
      })
    }
    return map
  }, [subjects])

  // --- Definição das Colunas ---
  const columns = [
    { key: 'code', label: 'Código UFCD' },
    { key: 'name', label: 'Nome' },
    { key: 'subject_name', label: 'Disciplina' },
    { key: 'hours_display', label: 'Carga Horária' }
  ]

  // --- Transformação dos Dados para Tabela ---
  const tableData = filteredModules.map(m => ({
    ...m,
    subject_name: subjectMap[m.subject_id] || 'N/A',
    hours_display: `${m.hours_total}h`
  }))

  // --- Handlers ---

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
      {/* --- CABEÇALHO --- */}
      <CRow className="mb-4 align-items-center">
        <CCol>
          <h2 className="mb-0 fw-bold text-dark">
            <CIcon icon={cilList} className="me-2 text-success" />
            Gestão de Módulos
          </h2>
          <small className="text-muted">Defina os módulos (UFCDs) e as suas cargas horárias.</small>
        </CCol>
        <CCol className="text-end">
          <CButton color="primary" onClick={handleCreate} className="d-flex align-items-center gap-2 ms-auto">
            <CIcon icon={cilPlus} />
            Novo Módulo
          </CButton>
        </CCol>
      </CRow>

      {/* --- FILTRO --- */}
      <CCard className="border-0 shadow-sm mb-4">
        <CCardBody>
          <CRow>
            <CCol md={4}>
              <CFormSelect
                label="Filtrar por Disciplina"
                value={filterSubjectId}
                onChange={(e) => setFilterSubjectId(e.target.value)}
              >
                <option value="">-- Todas as Disciplinas --</option>
                {(subjects || []).map(s => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </CFormSelect>
            </CCol>
          </CRow>
        </CCardBody>
      </CCard>

      {/* --- ERROS DE ELIMINAÇÃO --- */}
      {deleteMutation.isError && (
        <CAlert color="danger" dismissible onClose={deleteMutation.reset}>
          <strong>Erro ao remover:</strong> {deleteMutation.error?.response?.data?.detail || "Ocorreu um erro."}
        </CAlert>
      )}

      {/* --- TABELA --- */}
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

      {/* --- MODAL GENÉRICO --- */}
      <GenericModalForm
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
        title="Módulo"
        initialData={selectedItem}
        FormComponent={ModuleForm}
        onSubmit={handleFormSubmit}
        isLoading={activeMutation.isPending}
        error={activeMutation.error}
      />
    </div>
  )
}

export default Modules
