import React, { useState, useEffect } from 'react'
import PropTypes from 'prop-types'
import {
  CForm, CCol, CRow, CFormInput, CButton, CModalFooter, CFormSelect
} from '@coreui/react'
import { useCourses } from '../../hooks/useSchoolData'

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
        course_id: initialData.course_id ? String(initialData.course_id) : ''
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
    // Pequena proteção: converter string vazia em null para o backend
    const finalData = {
        ...formData,
        course_id: formData.course_id ? Number.parseInt(formData.course_id, 10) : null
    }
    onSubmit(finalData)
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
            label="Curso Associado"
            name="course_id"
            value={formData.course_id}
            onChange={handleChange}
            text="Associe esta turma a um curso profissional para gerir disciplinas e professores na página da turma."
          >
            <option value="">-- Sem Curso --</option>
            {/* Lista dinâmica de cursos */}
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

ClassForm.propTypes = {
  initialData: PropTypes.object,
  onSubmit: PropTypes.func.isRequired,
  isLoading: PropTypes.bool,
  onCancel: PropTypes.func.isRequired,
}