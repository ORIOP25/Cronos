import React, { useState, useEffect } from 'react'
import {
  CForm, CRow, CFormInput, CButton, CModalFooter, CFormSelect
} from '@coreui/react'

const RoomForm = ({ initialData, onSubmit, isLoading, onCancel }) => {
  const [formData, setFormData] = useState({ 
    name: '', 
    type: 'normal',
    capacity: 30
  })

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

  const handleChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    onSubmit(formData)
  }

  return (
    <CForm onSubmit={handleSubmit}>
      <CRow className="g-3">
        <CCol md={8}>
          <CFormInput
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
          {isLoading ? 'A gravar...' : (initialData ? 'Atualizar Sala' : 'Criar Sala')}
        </CButton>
      </CModalFooter>
    </CForm>
  )
}

export default RoomForm