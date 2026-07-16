import { useState } from 'react'
import PageHeader from '../components/PageHeader'
import { CButton, CAlert, CBadge } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilPlus } from '@coreui/icons'

import SmartTable from '../components/SmartTable'
import GenericModalForm from '../components/GenericModalForm'
import RoomForm from '../components/Forms/RoomForm'
import RoomTypeBadge from '../components/RoomTypeBadge'
import { getApiErrorMessage } from '../utils/apiErrors'

// Hooks (Factory)
import { 
  useRooms, 
  useCreateRoom,
  useUpdateRoom,
  useDeleteRoom,
} from '../features/catalog/data'

const Rooms = () => {
  const [modalVisible, setModalVisible] = useState(false)
  const [selectedItem, setSelectedItem] = useState(null)

  // 1. Hooks de Dados
  const { data: rooms, isLoading, isError, error, refetch } = useRooms()
  const createMutation = useCreateRoom()
  const updateMutation = useUpdateRoom()
  const deleteMutation = useDeleteRoom()

  // 2. Colunas
  const columns = [
    { key: 'name', label: 'Sala' },
    { key: 'capacity', label: 'Lotação', render: (room) => <CBadge color="info">{room.capacity} alunos</CBadge> },
    { key: 'type', label: 'Tipo', render: (room) => <RoomTypeBadge type={room.type} /> }
  ]

  // --- Handlers ---

  const handleCreate = () => {
    setSelectedItem(null)
    setModalVisible(true)
  }

  const handleEdit = (item) => {
    setSelectedItem(item)
    setModalVisible(true)
  }

  const handleDelete = (id) => deleteMutation.mutateAsync(id)

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
          <strong>Erro ao remover:</strong> {getApiErrorMessage(deleteMutation.error, 'Erro de dependência.')}
        </CAlert>
      )}

      <SmartTable
            columns={columns}
            data={rooms || []}
            isLoading={isLoading}
            isError={isError}
            error={error}
            onRetry={() => refetch()}
            actions={true}
            onEdit={handleEdit}
            onDelete={handleDelete}
            getRowLabel={(room) => room.name}
          />

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
