import React, { useState, useEffect } from 'react'
import {
  CForm, CCol, CRow, CFormInput, CButton, CModalFooter
} from '@coreui/react'

const ClassForm = ({ initialData, onSubmit, isLoading, onCancel }) => {
  const { data: courses } = useCourses()
  const [formData, setFormData] = useState({ 
    name: '', 
    size: 25,
    course_id: ''
  })

  // Popula o formulário se estivermos a editar
  useEffect(() => {
    if (initialData) {
      setFormData({
        name: initialData.name || '',
        size: initialData.size || 25,
        course_id: initialData.course_id || ''
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

        <CCol md={12}>
          <CFormSelect
            label="Curso Associado (Opcional)"
            name="course_id"
            value={formData.course_id}
            onChange={handleChange}
            text="Associe esta turma a um curso profissional."
          >
            <option value="">-- Sem Curso --</option>
            {courses?.map(course => (
                <option key={course.id} value={course.id}>{course.name}</option>
            ))}
          </CFormSelect>
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