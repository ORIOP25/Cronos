import { useRef, useState } from 'react'
import { CButton, CForm, CFormInput, CModal, CModalBody, CModalHeader, CModalTitle } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilPencil, cilTrash } from '@coreui/icons'
import { toast } from 'react-hot-toast'
import ConfirmationModal from './ConfirmationModal'
import FeedbackBanner from './FeedbackBanner'
import StatePanel from './StatePanel'
import { TXT } from '../utils/terminology'
import {
  getApiErrorMessage,
  getRoomTypeErrorMessage,
  isApiErrorTransient,
  ROOM_TYPE_NAME_MESSAGE,
} from '../utils/apiErrors'
import { useAttemptScope } from '../hooks/useAttemptScope'
import {
  useCreateRoomType,
  useDeleteRoomType,
  useRoomTypes,
  useUpdateRoomType,
} from '../features/catalog/data'

const NAME_MAX_LENGTH = 60
const TRANSIENT_TOAST_MS = 6000

const isValidName = (name) => name.length > 0 && name.length <= NAME_MAX_LENGTH

/** Reports a failed write: transient failures toast, business blocks stay in the modal. */
const reportFailure = (failure, showInContext) => {
  if (isApiErrorTransient(failure)) {
    toast.error(getApiErrorMessage(failure, TXT.ERROR_SAVING), { duration: TRANSIENT_TOAST_MS })
    return
  }
  showInContext(getRoomTypeErrorMessage(failure))
}

const RoomTypeActions = ({ roomType, onEdit, onRemove }) => {
  if (roomType.is_normal) return <span className="text-muted">Fixo</span>
  return (
    <div className="d-flex justify-content-end align-items-center gap-2">
      <button
        className="btn-zen-ghost zen-table-action-trigger"
        onClick={() => onEdit(roomType)}
        title={TXT.EDIT}
        aria-label={`${TXT.EDIT} ${roomType.name}`}
        type="button"
      >
        <CIcon icon={cilPencil} size="sm" />
      </button>
      <button
        className="btn-zen-ghost zen-table-action-trigger text-danger"
        onClick={() => onRemove(roomType)}
        title={TXT.REMOVE}
        aria-label={`${TXT.REMOVE} ${roomType.name}`}
        type="button"
      >
        <CIcon icon={cilTrash} size="sm" />
      </button>
    </div>
  )
}

const RoomTypesTable = ({ roomTypes, onEdit, onRemove }) => (
  <table className="zen-table">
    <thead>
      <tr>
        <th>Nome</th>
        <th>Salas</th>
        <th>Disciplinas</th>
        <th className="text-end">Ações</th>
      </tr>
    </thead>
    <tbody>
      {roomTypes.map((roomType) => (
        <tr key={roomType.id}>
          <td>{roomType.name}</td>
          <td>{roomType.room_count}</td>
          <td>{roomType.subject_count}</td>
          <td className="text-end">
            <RoomTypeActions roomType={roomType} onEdit={onEdit} onRemove={onRemove} />
          </td>
        </tr>
      ))}
    </tbody>
  </table>
)

/**
 * Janela "Tipos de sala" da página Salas. Lista os tipos da escola e cria,
 * renomeia ou remove. O tipo Normal é fixo.
 */
const RoomTypesModal = ({ onClose }) => {
  const { data: roomTypes = [], isLoading, isError, error, refetch } = useRoomTypes()
  const createMutation = useCreateRoomType()
  const updateMutation = useUpdateRoomType()
  const deleteMutation = useDeleteRoomType()
  const attemptScope = useAttemptScope()
  const [draftName, setDraftName] = useState('')
  const [editing, setEditing] = useState(null)
  const [removing, setRemoving] = useState(null)
  const [formError, setFormError] = useState('')
  const [listError, setListError] = useState('')
  const nameInputRef = useRef(null)
  const isSaving = createMutation.isPending || updateMutation.isPending

  const resetForm = () => {
    setEditing(null)
    setDraftName('')
    setFormError('')
  }

  const startEdit = (roomType) => {
    setEditing(roomType)
    setDraftName(roomType.name)
    setFormError('')
    nameInputRef.current?.focus()
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    const name = draftName.trim()
    if (!isValidName(name)) {
      setFormError(ROOM_TYPE_NAME_MESSAGE)
      nameInputRef.current?.focus()
      return
    }
    const attempt = attemptScope.capture()
    setFormError('')
    try {
      if (editing) {
        await updateMutation.mutateAsync({ id: editing.id, name })
        if (!attemptScope.isCurrent(attempt)) return
        toast.success('Tipo de sala atualizado.')
      } else {
        await createMutation.mutateAsync({ name })
        if (!attemptScope.isCurrent(attempt)) return
        toast.success('Tipo de sala criado.')
      }
      resetForm()
    } catch (failure) {
      if (!attemptScope.isCurrent(attempt)) return
      reportFailure(failure, setFormError)
    }
  }

  const handleRemoveConfirm = async () => {
    const attempt = attemptScope.capture()
    setListError('')
    try {
      const result = await deleteMutation.mutateAsync(removing.id)
      if (!attemptScope.isCurrent(attempt)) return
      toast.success(result?.remove_effect === 'archive' ? TXT.RECORD_ARCHIVED : TXT.RECORD_REMOVED)
      setRemoving(null)
    } catch (failure) {
      if (!attemptScope.isCurrent(attempt)) return
      setRemoving(null)
      reportFailure(failure, setListError)
    }
  }

  let content
  if (isLoading) {
    content = <StatePanel state="loading" title={TXT.LOADING} />
  } else if (isError) {
    content = (
      <StatePanel
        state="error"
        title="Erro ao carregar"
        description={getApiErrorMessage(error, TXT.ERROR_LOADING)}
        action={<button className="btn btn-outline-primary" type="button" onClick={() => refetch()}>Tentar novamente</button>}
      />
    )
  } else {
    content = <RoomTypesTable roomTypes={roomTypes} onEdit={startEdit} onRemove={setRemoving} />
  }

  return (
    <CModal visible alignment="center" scrollable size="lg" onClose={onClose} aria-labelledby="room-types-title">
      <CModalHeader onClose={onClose}>
        <CModalTitle id="room-types-title">Tipos de sala</CModalTitle>
      </CModalHeader>
      <CModalBody>
        <CForm onSubmit={handleSubmit} className="mb-4">
          <CFormInput
            id="room-type-name"
            ref={nameInputRef}
            label="Nome do tipo de sala"
            value={draftName}
            onChange={(event) => {
              setDraftName(event.target.value)
              setFormError('')
            }}
            aria-invalid={formError ? true : undefined}
            aria-describedby={formError ? 'room-type-form-error' : undefined}
          />
          {formError && (
            <div id="room-type-form-error" className="mt-2">
              <FeedbackBanner tone="danger">{formError}</FeedbackBanner>
            </div>
          )}
          <div className="d-flex gap-2 mt-3">
            <CButton type="submit" color="primary" disabled={isSaving}>
              {editing ? 'Guardar nome' : 'Novo tipo'}
            </CButton>
            {editing && (
              <CButton type="button" color="secondary" variant="ghost" onClick={resetForm}>
                Cancelar edição
              </CButton>
            )}
          </div>
        </CForm>

        {listError && <div className="mb-3"><FeedbackBanner tone="danger">{listError}</FeedbackBanner></div>}
        {content}
      </CModalBody>

      <ConfirmationModal
        visible={removing !== null}
        onClose={() => setRemoving(null)}
        onConfirm={handleRemoveConfirm}
        message={`Remover o tipo ${removing?.name ?? ''}? Se uma sala ou disciplina ativa o usar, a remoção fica bloqueada.`}
        isLoading={deleteMutation.isPending}
      />
    </CModal>
  )
}

export default RoomTypesModal
