import { useState } from 'react'
import {
  CForm, CFormFeedback, CRow, CCol, CFormInput, CButton, CModalFooter, CFormSelect
} from '@coreui/react'
import { portugueseValidityProps } from '../../utils/formValidity'
import { useRoomTypes } from '../../features/catalog/data'

const RoomForm = ({ initialData, onSubmit, isLoading, onCancel }) => {
  const { data: roomTypes = [], isLoading: roomTypesLoading, isError: roomTypesError, refetch } = useRoomTypes()
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
    if (roomTypesLoading || roomTypesError || !normalRoomType) return
    const name = String(formData.name ?? '').trim()
    if (!name) {
      setError('Nome da sala é obrigatório.')
      document.getElementById('room-name')?.focus()
      return
    }
    onSubmit({
      ...formData,
      name,
      room_type_id: Number(formData.room_type_id || normalRoomType.id),
      capacity: Number(formData.capacity),
    })
  }

  let submitLabel = 'Criar Sala'
  if (isLoading) submitLabel = 'A gravar...'
  else if (initialData) submitLabel = 'Atualizar Sala'

  return (
    <CForm onSubmit={handleSubmit}>
      <CRow className="g-3">
        <CCol md={8}>
          <CFormInput
            id="room-name"
            type="text"
            label="Nome da Sala"
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
            label="Tipo de Sala"
            name="room_type_id"
            value={String(formData.room_type_id || normalRoomType?.id || '')}
            onChange={handleChange}
            disabled={roomTypesLoading || roomTypesUnavailable}
            required
            aria-invalid={roomTypesErrorMessage ? 'true' : undefined}
            aria-describedby={roomTypesLoading ? 'room-types-loading' : roomTypesErrorMessage ? 'room-types-error' : undefined}
          >
            {roomTypes.map((roomType) => <option key={roomType.id} value={roomType.id}>{roomType.name}</option>)}
          </CFormSelect>
          {roomTypesLoading && <div id="room-types-loading" role="status" aria-live="polite" className="form-text">A carregar tipos de sala…</div>}
          {roomTypesErrorMessage && (
            <div id="room-types-error">
              <CFormFeedback invalid className="d-block" role="alert">{roomTypesErrorMessage}</CFormFeedback>
              {roomTypesError && <CButton type="button" color="secondary" variant="ghost" size="sm" onClick={() => refetch()}>Tentar novamente</CButton>}
            </div>
          )}
        </CCol>
      </CRow>

      <CModalFooter className="px-0 mt-4 border-0 pb-0">
        <CButton color="secondary" variant="ghost" onClick={onCancel}>
          Cancelar
        </CButton>
        <CButton color="primary" type="submit" disabled={isLoading || roomTypesLoading || roomTypesUnavailable}>
          {submitLabel}
        </CButton>
      </CModalFooter>
    </CForm>
  )
}

export default RoomForm
