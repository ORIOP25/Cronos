import { useState } from 'react'
import {
  CForm, CRow, CCol, CFormInput, CButton, CModalFooter, CFormSelect
} from '@coreui/react'
import { ROOM_TYPES } from '../../utils/presentation'

const RoomForm = ({ initialData, onSubmit, isLoading, onCancel }) => {
  const [formData, setFormData] = useState(() => ({
    name: initialData?.name || '',
    type: initialData?.type || 'normal',
    capacity: initialData?.capacity || 30,
  }))

  const handleChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({
      ...prev,
      [name]: name === 'capacity' && value !== '' ? Number(value) : value,
    }))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    onSubmit({
      ...formData,
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
          />
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
          />
        </CCol>

        <CCol md={12}>
          <CFormSelect 
            id="room-type"
            label="Tipo de Sala" 
            name="type"
            value={formData.type}
            onChange={handleChange}
          >
            {Object.entries(ROOM_TYPES).map(([value, metadata]) => <option key={value} value={value}>{metadata.label}</option>)}
          </CFormSelect>
        </CCol>
      </CRow>

      <CModalFooter className="px-0 mt-4 border-0 pb-0">
        <CButton color="secondary" variant="ghost" onClick={onCancel}>
          Cancelar
        </CButton>
        <CButton color="primary" type="submit" disabled={isLoading}>
          {submitLabel}
        </CButton>
      </CModalFooter>
    </CForm>
  )
}

export default RoomForm
