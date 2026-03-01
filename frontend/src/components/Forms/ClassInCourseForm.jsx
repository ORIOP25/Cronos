import React, { useEffect, useState } from 'react'
import {
  CForm,
  CRow,
  CCol,
  CFormInput,
  CButton,
  CModalFooter,
} from '@coreui/react'
import PropTypes from 'prop-types'

const defaultState = {
  name: '',
  size: 25,
  grade_level: 10,
  start_year: new Date().getFullYear(),
  end_year: new Date().getFullYear() + 3,
}

const ClassInCourseForm = ({ initialData, onSubmit, isLoading, onCancel }) => {
  const [formData, setFormData] = useState(defaultState)

  useEffect(() => {
    if (initialData) {
      setFormData({
        name: initialData.name || '',
        size: initialData.size || 25,
        grade_level: initialData.grade_level || 10,
        start_year: initialData.start_year || new Date().getFullYear(),
        end_year: initialData.end_year || new Date().getFullYear() + 3,
      })
      return
    }
    setFormData(defaultState)
  }, [initialData])

  const handleChange = (e) => {
    const { name, value } = e.target
    setFormData((prev) => ({ ...prev, [name]: value }))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    onSubmit({
      name: String(formData.name).trim(),
      size: Number(formData.size),
      grade_level: Number(formData.grade_level),
      start_year: Number(formData.start_year),
      end_year: Number(formData.end_year),
    })
  }

  let submitLabel = 'Criar Turma'
  if (isLoading) submitLabel = 'A gravar...'
  else if (initialData) submitLabel = 'Atualizar Turma'

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
            placeholder="Ex: TGPSI 10A"
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
            max="100"
            required
          />
        </CCol>

        <CCol md={4}>
          <CFormInput
            type="number"
            label="Ano (10-12)"
            name="grade_level"
            value={formData.grade_level}
            onChange={handleChange}
            min="10"
            max="12"
            required
          />
        </CCol>

        <CCol md={4}>
          <CFormInput
            type="number"
            label="Início"
            name="start_year"
            value={formData.start_year}
            onChange={handleChange}
            min="2000"
            required
          />
        </CCol>

        <CCol md={4}>
          <CFormInput
            type="number"
            label="Fim"
            name="end_year"
            value={formData.end_year}
            onChange={handleChange}
            min="2001"
            required
          />
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

ClassInCourseForm.propTypes = {
  initialData: PropTypes.shape({
    name: PropTypes.string,
    size: PropTypes.number,
    grade_level: PropTypes.number,
    start_year: PropTypes.number,
    end_year: PropTypes.number,
  }),
  onSubmit: PropTypes.func.isRequired,
  isLoading: PropTypes.bool,
  onCancel: PropTypes.func.isRequired,
}

export default ClassInCourseForm
