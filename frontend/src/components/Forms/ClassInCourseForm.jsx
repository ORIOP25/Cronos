import { useState } from 'react'
import {
  CForm,
  CRow,
  CCol,
  CFormInput,
  CButton,
  CModalFooter,
  CAlert,
} from '@coreui/react'
import { createClassDraft, validateClassDraft } from '../../utils/classDraft'
import { portugueseValidityProps } from '../../utils/formValidity'

const ClassInCourseForm = ({ initialData, onSubmit, isLoading, onCancel }) => {
  const [formData, setFormData] = useState(() => createClassDraft(initialData))
  const [error, setError] = useState('')

  const handleChange = (e) => {
    const { name, value } = e.target
    setError('')
    setFormData((prev) => ({ ...prev, [name]: value }))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    const validation = validateClassDraft(formData)
    if (validation.error) return setError(validation.error)
    onSubmit(validation.value)
  }

  let submitLabel = 'Criar Turma'
  if (isLoading) submitLabel = 'A gravar...'
  else if (initialData) submitLabel = 'Atualizar Turma'

  return (
    <CForm onSubmit={handleSubmit}>
      {error && <CAlert color="danger" id="class-form-error">{error}</CAlert>}

      <CRow className="g-3">
        <CCol md={8}>
          <CFormInput
            id="classInCourseName"
            type="text"
            label="Nome da Turma"
            name="name"
            value={formData.name}
            onChange={handleChange}
            required
            placeholder="Ex: TGPSI 10A"
            invalid={Boolean(error)}
            aria-describedby={error ? 'class-form-error' : undefined}
            {...portugueseValidityProps}
          />
        </CCol>

        <CCol md={4}>
          <CFormInput
            id="classInCourseSize"
            type="number"
            label="Nº Alunos"
            name="size"
            value={formData.size}
            onChange={handleChange}
            min="1"
            max="100"
            required
            {...portugueseValidityProps}
          />
        </CCol>

        <CCol md={4}>
          <CFormInput
            id="classInCourseGradeLevel"
            type="number"
            label="Ano (10-12)"
            name="grade_level"
            value={formData.grade_level}
            onChange={handleChange}
            min="10"
            max="12"
            required
            {...portugueseValidityProps}
          />
        </CCol>

        <CCol md={4}>
          <CFormInput
            id="classInCourseStartYear"
            type="number"
            label="Início"
            name="start_year"
            value={formData.start_year}
            onChange={handleChange}
            min="2000"
            required
            {...portugueseValidityProps}
          />
        </CCol>

        <CCol md={4}>
          <CFormInput
            id="classInCourseEndYear"
            type="number"
            label="Fim"
            name="end_year"
            value={formData.end_year}
            onChange={handleChange}
            min="2001"
            required
            {...portugueseValidityProps}
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

export default ClassInCourseForm
