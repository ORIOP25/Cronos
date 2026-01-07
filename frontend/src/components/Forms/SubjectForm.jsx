import React, { useState, useEffect } from 'react'
import {
  CForm, CCol, CRow, CFormInput, CButton, CModalFooter, CFormSelect
} from '@coreui/react'

const SubjectForm = ({ initialData, onSubmit, isLoading, onCancel }) => {
  const [formData, setFormData] = useState({ 
    name: '', 
    required_room_type: 'normal' 
  })

  // Popula o formulário se estivermos a editar
  useEffect(() => {
    if (initialData) {
      setFormData({
        name: initialData.name || '',
        required_room_type: initialData.required_room_type || 'normal'
      })
    } else {
        setFormData({ name: '', required_room_type: 'normal' })
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
            label="Nome da Disciplina"
            name="name"
            value={formData.name}
            onChange={handleChange}
            required
            placeholder="Ex: Matemática, Ed. Física"
          />
        </CCol>
        
        <CCol md={4}>
          <CFormSelect 
            label="Sala Obrigatória" 
            name="required_room_type"
            value={formData.required_room_type}
            onChange={handleChange}
            text="Onde deve decorrer a aula?"
          >
            <option value="normal">Sala Normal</option>
            <option value="lab">Laboratório</option>
            <option value="gym">Ginásio</option>
            <option value="art">Artes / Atelier</option>
          </CFormSelect>
        </CCol>
      </CRow>

      <CModalFooter className="px-0 mt-4 border-0 pb-0">
        <CButton color="secondary" variant="ghost" onClick={onCancel}>
          Cancelar
        </CButton>
        <CButton color="primary" type="submit" disabled={isLoading}>
          {isLoading ? 'A gravar...' : (initialData ? 'Atualizar Disciplina' : 'Criar Disciplina')}
        </CButton>
      </CModalFooter>
    </CForm>
  )
}

export default SubjectForm