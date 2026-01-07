import React, { useState, useEffect } from 'react'
import {
  CForm, CCol, CRow, CFormInput, CButton, CModalFooter
} from '@coreui/react'

const ClassForm = ({ initialData, onSubmit, isLoading, onCancel }) => {
  const [formData, setFormData] = useState({ 
    name: '', 
    size: 25 
  })

  // Popula o formulário se estivermos a editar
  useEffect(() => {
    if (initialData) {
      setFormData({
        name: initialData.name || '',
        size: initialData.size || 25
      })
    } else {
        setFormData({ name: '', size: 25 })
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
            label="Nome da Turma"
            name="name"
            value={formData.name}
            onChange={handleChange}
            required
            placeholder="Ex: 12º A"
          />
        </CCol>
        
        <CCol md={4}>
          <CFormInput
            type="number"
            label="Nº Alunos"
            name="size"
            value={formData.size}
            onChange={handleChange}
            min="1"
            required
            text="Usado para validar a lotação da sala."
          />
        </CCol>
      </CRow>

      <CModalFooter className="px-0 mt-4 border-0 pb-0">
        <CButton color="secondary" variant="ghost" onClick={onCancel}>
          Cancelar
        </CButton>
        <CButton color="primary" type="submit" disabled={isLoading}>
          {isLoading ? 'A gravar...' : (initialData ? 'Atualizar Turma' : 'Criar Turma')}
        </CButton>
      </CModalFooter>
    </CForm>
  )
}

export default ClassForm