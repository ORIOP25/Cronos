import { useState } from 'react'
import { TXT } from '../../utils/terminology'
import { toast } from 'react-hot-toast'
import {
  CForm, CFormFeedback, CRow, CCol, CFormInput, CButton, CModalFooter, CFormSelect
} from '@coreui/react'
import { portugueseValidityProps } from '../../utils/formValidity'
import { useCreateRoomType, useRoomTypes } from '../../features/catalog/data'
import RoomTypesModal from '../RoomTypesModal'
import { getRoomTypeErrorMessage, ROOM_TYPE_NAME_MESSAGE } from '../../utils/apiErrors'
import { useAttemptScope } from '../../hooks/useAttemptScope'

const RoomForm = ({ initialData, onSubmit, isLoading, onCancel }) => {
  const { data: roomTypes = [], isLoading: roomTypesLoading, isError: roomTypesError, refetch } = useRoomTypes()
  const createType = useCreateRoomType()
  const attemptScope = useAttemptScope()
  const [addingType, setAddingType] = useState(false)
  const [typeName, setTypeName] = useState('')
  const [typeError, setTypeError] = useState('')
  const [createdType, setCreatedType] = useState(null)
  const [managingTypes, setManagingTypes] = useState(false)
  const availableTypes = createdType && !roomTypes.some((type) => type.id === createdType.id) ? [...roomTypes, createdType] : roomTypes

  const addType = async () => {
    const name = typeName.trim()
    if (!name || name.length > 60) {
      setTypeError(ROOM_TYPE_NAME_MESSAGE)
      document.getElementById('room-new-type')?.focus()
      return
    }
    const attempt = attemptScope.capture()
    setTypeError('')
    try {
      const roomType = await createType.mutateAsync({ name })
      if (!attemptScope.isCurrent(attempt)) return
      setCreatedType(roomType)
      setFormData((current) => ({ ...current, room_type_id: roomType.id }))
      setAddingType(false)
      setTypeName('')
      toast.success('Tipo de sala criado.')
    } catch (failure) {
      if (!attemptScope.isCurrent(attempt)) return
      setTypeError(getRoomTypeErrorMessage(failure))
    }
  }
  const normalRoomType = roomTypes.find((roomType) => roomType.is_normal)
  const roomTypesUnavailable = !roomTypesLoading && (roomTypesError || !normalRoomType)
  const roomTypesErrorMessage = roomTypesError
    ? 'Não foi possível carregar os tipos de sala.'
    : !roomTypesLoading && !normalRoomType
      ? 'Não existem tipos de sala disponíveis.'
      : ''
  const [formData, setFormData] = useState(() => ({
    name: initialData?.name || '',
    room_type_id: initialData?.room_type?.id ?? initialData?.room_type_id ?? '',
    capacity: initialData?.capacity || 30,
  }))
  const [error, setError] = useState('')
  const selectedRoomTypeId = availableTypes.find((type) => type.id === Number(formData.room_type_id))?.id ?? normalRoomType?.id ?? ''

  const handleChange = (e) => {
    const { name, value } = e.target
    setError('')
    setFormData(prev => ({
      ...prev,
      [name]: name === 'capacity' && value !== '' ? Number(value) : value,
    }))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (roomTypesLoading || roomTypesError || !normalRoomType || createType.isPending || addingType) return
    const name = String(formData.name ?? '').trim()
    if (!name) {
      setError('Nome da sala é obrigatório.')
      document.getElementById('room-name')?.focus()
      return
    }
    onSubmit({
      ...formData,
      name,
      room_type_id: Number(selectedRoomTypeId),
      capacity: Number(formData.capacity),
    })
  }

  let submitLabel = 'Criar sala'
  if (isLoading) submitLabel = TXT.SAVING
  else if (initialData) submitLabel = TXT.SAVE_CHANGES

  return (
    <>
    <CForm onSubmit={handleSubmit} className={managingTypes ? 'd-none' : undefined}>
      <CRow className="g-3">
        <CCol md={8}>
          <CFormInput
            id="room-name"
            type="text"
            label="Nome da sala"
            name="name"
            value={formData.name}
            onChange={handleChange}
            required
            placeholder="Ex: C4, Lab Química"
            invalid={Boolean(error)}
            aria-invalid={Boolean(error) || undefined}
            aria-describedby={error ? 'room-form-error' : undefined}
            {...portugueseValidityProps}
          />
          {error && <CFormFeedback id="room-form-error" invalid className="d-block" role="alert">{error}</CFormFeedback>}
        </CCol>
        
        <CCol md={4}>
          <CFormInput
            id="room-capacity"
            type="number"
            label="Lotação"
            name="capacity"
            value={formData.capacity}
            onChange={handleChange}
            min="1"
            required
            {...portugueseValidityProps}
          />
        </CCol>

        <CCol md={12}>
          <CFormSelect
            id="room-type"
            label="Tipo de sala"
            name="room_type_id"
            value={String(selectedRoomTypeId)}
            onChange={handleChange}
            disabled={roomTypesLoading || roomTypesUnavailable}
            required
            aria-invalid={roomTypesErrorMessage ? 'true' : undefined}
            aria-describedby={roomTypesLoading ? 'room-types-loading' : roomTypesErrorMessage ? 'room-types-error' : undefined}
          >
            {availableTypes.map((roomType) => <option key={roomType.id} value={roomType.id}>{roomType.name}</option>)}
          </CFormSelect>
          <div className="d-flex gap-3 mt-1">
            <CButton type="button" color="link" className="p-0" disabled={isLoading || roomTypesLoading || createType.isPending} onClick={() => setAddingType(true)}>Adicionar tipo de sala</CButton>
            <CButton type="button" color="link" className="p-0" disabled={isLoading || createType.isPending} onClick={() => { setCreatedType(null); setManagingTypes(true) }}>Gerir tipos existentes</CButton>
          </div>
          {addingType && <div className="mt-3">
            <CFormInput id="room-new-type" label="Nome do novo tipo" value={typeName} autoFocus disabled={createType.isPending} onChange={(event) => { setTypeName(event.target.value); setTypeError('') }} aria-invalid={Boolean(typeError)} aria-describedby={typeError ? 'room-new-type-error' : undefined} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); void addType() } }} />
            {typeError && <div id="room-new-type-error" className="invalid-feedback d-block" role="alert">{typeError}</div>}
            <div className="d-flex gap-2 mt-2">
              <CButton type="button" color="primary" disabled={createType.isPending} onClick={() => void addType()}>{createType.isPending ? 'A criar…' : 'Criar tipo de sala'}</CButton>
              <CButton type="button" color="secondary" variant="outline" disabled={createType.isPending} onClick={() => { setAddingType(false); setTypeError('') }}>Cancelar tipo</CButton>
            </div>
          </div>}
          {roomTypesLoading && <div id="room-types-loading" role="status" aria-live="polite" className="form-text">A carregar tipos de sala…</div>}
          {roomTypesErrorMessage && (
            <div id="room-types-error">
              <CFormFeedback invalid className="d-block" role="alert">{roomTypesErrorMessage}</CFormFeedback>
              {roomTypesError && <CButton type="button" color="secondary" variant="outline" size="sm" onClick={() => refetch()}>Tentar novamente</CButton>}
            </div>
          )}
        </CCol>
      </CRow>

      <CModalFooter className="px-0 mt-4 border-0 pb-0">
        <CButton color="secondary" variant="outline" onClick={onCancel}>
          Cancelar
        </CButton>
        <CButton color="primary" type="submit" disabled={isLoading || roomTypesLoading || roomTypesUnavailable || createType.isPending || addingType}>
          {submitLabel}
        </CButton>
      </CModalFooter>
    </CForm>
    {managingTypes && <RoomTypesModal embedded onClose={() => { setManagingTypes(false); document.getElementById('room-type')?.focus() }} />}
    </>
  )
}

export default RoomForm
