import React, { useState } from 'react'
import PageHeader from '../components/PageHeader'
import { 
  CCard, CCardBody, CButton, CAlert, CBadge 
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilPlus } from '@coreui/icons'

import SmartTable from '../components/SmartTable'
import GenericModalForm from '../components/GenericModalForm'
import RoomForm from '../components/Forms/RoomForm'

// Hooks (Factory)
import { 
  useRooms, 
  useCreateEntity, 
  useUpdateEntity, 
  useDeleteEntity 
} from '../hooks/useSchoolData'

function mapRoomType(type) {
  const map = {
    'normal': 'Normal',
    'lab': 'Laboratório',
    'gym': 'Ginásio',
    'art': 'Artes'
  }
  return map[type] || type
}

const Rooms = () => {
  const [modalVisible, setModalVisible] = useState(false)
  const [selectedItem, setSelectedItem] = useState(null)

  // 1. Hooks de Dados
  // Nota: 'rooms' é a key que definimos no useSchoolData
  const { data: rooms, isLoading, isError, error, refetch } = useRooms()
  const createMutation = useCreateEntity('rooms')
  const updateMutation = useUpdateEntity('rooms')
  const deleteMutation = useDeleteEntity('rooms')

  // 2. Colunas
  const columns = [
    { key: 'name', label: 'Sala' },
    { key: 'capacity_badge', label: 'Lotação' },
    { key: 'type_label', label: 'Tipo' }
  ]

  // 3. Transformação de Dados (ViewModel)
  const tableData = (rooms || []).map(r => ({
    ...r,
    capacity_badge: <CBadge color="info">{r.capacity} alunos</CBadge>,
    type_label: mapRoomType(r.type)
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
      <PageHeader preTitle="Gestão" title="Salas" />
      <div className="d-flex justify-content-end mb-4">
        <CButton color="primary" onClick={handleCreate} className="d-flex align-items-center gap-2">
          <CIcon icon={cilPlus} />
          Nova Sala
        </CButton>
      </div>

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
        title="Sala"
        initialData={selectedItem}
        FormComponent={RoomForm}
        onSubmit={handleFormSubmit}
        isLoading={activeMutation.isPending}
        error={activeMutation.error}
      />
    </div>
  )
}

export default Rooms