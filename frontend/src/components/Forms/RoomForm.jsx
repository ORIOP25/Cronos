import React, { useState, useEffect } from 'react'
import PropTypes from 'prop-types'
import {
  CForm, CRow, CCol, CFormInput, CButton, CModalFooter, CFormSelect
} from '@coreui/react'

const RoomForm = ({ initialData, onSubmit, isLoading, onCancel }) => {
  const [formData, setFormData] = useState({ 
    name: '', 
    type: 'normal',
    capacity: 30
  })

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (initialData) {
      setFormData({
        name: initialData.name || '',
        type: initialData.type || 'normal',
        capacity: initialData.capacity || 30
      })
    } else {
        setFormData({ name: '', type: 'normal', capacity: 30 })
    }
  }, [initialData])
  /* eslint-enable react-hooks/set-state-in-effect */

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
            <option value="normal">Sala de Aula Normal</option>
            <option value="lab">Laboratório</option>
            <option value="gym">Ginásio / Desporto</option>
            <option value="art">Artes / Atelier</option>
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

RoomForm.propTypes = {
  initialData: PropTypes.shape({
    name: PropTypes.string,
    type: PropTypes.string,
    capacity: PropTypes.number,
  }),
  onSubmit: PropTypes.func.isRequired,
  isLoading: PropTypes.bool,
  onCancel: PropTypes.func.isRequired,
}

export default RoomForm
