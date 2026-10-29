import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'react-hot-toast'
import PageHeader from '../components/PageHeader'
import { CButton, CBadge } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilPlus } from '@coreui/icons'

import SmartTable from '../components/SmartTable'
import GenericModalForm from '../components/GenericModalForm'
import RoomForm from '../components/Forms/RoomForm'
import RoomTypeBadge from '../components/RoomTypeBadge'
import { getApiErrorMessage, joinNames } from '../utils/apiErrors'
import { useAttemptScope } from '../hooks/useAttemptScope'

// Hooks (Factory)
import { 
  useRooms, 
  useCreateRoom,
  useUpdateRoom,
  useDeleteRoom,
} from '../features/catalog/data'

const ROOM_DELETE_MESSAGE = 'As regras de configuração que a usam serão retiradas e o histórico de horários será preservado. Se estiver no horário atual, a remoção é bloqueada.'

const removeRoomMessage = (room) => {
  const classNames = (room.home_classes ?? []).map((turma) => turma.name)
  return classNames.length
    ? `${ROOM_DELETE_MESSAGE} É a sala da turma de ${joinNames(classNames)}. Essas turmas passam a Automática.`
    : ROOM_DELETE_MESSAGE
}

const Rooms = ({ readOnly = false, allowedActions }) => {
  const navigate = useNavigate()
  const [modalVisible, setModalVisible] = useState(false)
  const [selectedItem, setSelectedItem] = useState(null)

  // 1. Hooks de Dados
  const { data: rooms, isLoading, isError, error, refetch } = useRooms()
  const createMutation = useCreateRoom()
  const updateMutation = useUpdateRoom()
  const deleteMutation = useDeleteRoom()
  const attemptScope = useAttemptScope()
  const isTutorial = Array.isArray(allowedActions)
  const canUpdate = !readOnly && (!isTutorial || allowedActions.includes('UPDATE_ROOM'))
  const canCreate = !isTutorial && !readOnly
  const canDelete = !isTutorial && !readOnly

  // 2. Colunas
  const columns = [
    { key: 'name', label: 'Sala' },
    { key: 'capacity', label: 'Lotação', render: (room) => <CBadge color="info">{room.capacity} alunos</CBadge> },
    { key: 'room_type', label: 'Tipo', render: (room) => <RoomTypeBadge roomType={room.room_type} /> }
  ]

  // --- Handlers ---

  const handleCreate = () => {
    if (!canCreate) return
    setSelectedItem(null)
    setModalVisible(true)
  }

  const handleEdit = (item) => {
    if (!canUpdate) return
    setSelectedItem(item)
    setModalVisible(true)
  }

  const handleDelete = (id) => canDelete ? deleteMutation.mutateAsync(id) : Promise.resolve()

  const handleFormSubmit = async (formData) => {
    const attempt = attemptScope.capture()
    try {
      if (selectedItem) {
        await updateMutation.mutateAsync({ id: selectedItem.id, ...formData })
        if (!attemptScope.isCurrent(attempt)) return
        toast.success('Sala atualizada.')
      } else {
        await createMutation.mutateAsync(formData)
        if (!attemptScope.isCurrent(attempt)) return
        toast.success('Sala criada.')
      }
      setModalVisible(false)
    } catch (error) {
      if (!attemptScope.isCurrent(attempt)) return
      toast.error(getApiErrorMessage(error, 'Não foi possível guardar a sala. Tente novamente.'))
    }
  }

  const activeMutation = selectedItem ? updateMutation : createMutation

  return (
    <div className="p-4">
      <PageHeader title="Salas">
      {canCreate && <>
        <CButton color="secondary" variant="outline" onClick={() => navigate('/imports?resource=rooms')}>Importar CSV</CButton>
        <CButton color="primary" onClick={handleCreate} className="d-flex align-items-center gap-2" data-tutorial-target="new-room">
          <CIcon icon={cilPlus} />
          Nova Sala
        </CButton>
      </>}
      </PageHeader>

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
            allowEdit={canUpdate}
            allowDelete={canDelete}
            getRowLabel={(room) => room.name}
            deleteMessage={(room) => `Remover esta sala? ${removeRoomMessage(room)}`}
            bulkDeleteMessage={removeRoomMessage}
          />

      <GenericModalForm
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
        title="Sala"
        initialData={selectedItem}
        FormComponent={RoomForm}
        onSubmit={handleFormSubmit}
        isLoading={activeMutation.isPending}
        tutorialTarget="room-form"
      />

    </div>
  )
}

export default Rooms
