import React, { useState, useEffect } from 'react'
import {
  CForm, CCol, CRow, CFormInput, CButton, CModalFooter
} from '@coreui/react'

const TeacherForm = ({ initialData, onSubmit, isLoading, onCancel }) => {
  // Estado local do formulário
  const [formData, setFormData] = useState({ 
    name: '', 
    email: '' 
  })

  // Popula o formulário se estivermos em modo de Edição
  useEffect(() => {
    if (initialData) {
      setFormData({
        name: initialData.name || '',
        email: initialData.email || ''
      })
    } else {
        // Reset para criação
        setFormData({ name: '', email: '' })
    }
  }, [initialData])

  const handleChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    // Envia os dados para o componente pai (o Modal)
    onSubmit(formData)
  }

  return (
    <CForm onSubmit={handleSubmit}>
      <CRow className="g-3">
        <CCol md={12}>
          <CFormInput
            type="text"
            label="Nome Completo"
            name="name"
            value={formData.name}
            onChange={handleChange}
            required
            placeholder="Ex: Maria Silva"
          />
        </CCol>
        
        <CCol md={12}>
          <CFormInput
            type="email"
            label="Email Institucional"
            name="email"
            value={formData.email}
            onChange={handleChange}
            placeholder="Ex: maria.silva@escola.pt"
            text="Se preenchido, será criada uma conta de utilizador automaticamente."
          />
        </CCol>
      </CRow>

      {/* Footer do Formulário (Botões de Ação) */}
      <CModalFooter className="px-0 mt-4 border-0 pb-0">
        <CButton color="secondary" variant="ghost" onClick={onCancel}>
          Cancelar
        </CButton>
        <CButton color="primary" type="submit" disabled={isLoading}>
          {isLoading ? 'A gravar...' : 'Gravar'}
        </CButton>
      </CModalFooter>
    </CForm>
  )
}

export default TeacherForm