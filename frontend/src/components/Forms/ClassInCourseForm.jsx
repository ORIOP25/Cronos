import { useState } from 'react'
import {
  CForm,
  CRow,
  CCol,
  CFormInput,
  CButton,
  CModalFooter,
  CFormFeedback,
} from '@coreui/react'
import { createClassDraft, validateClassDraft } from '../../utils/classDraft'

const FEEDBACK_ID = 'classInCourseValidation'
const FIELD_IDS = {
  name: 'classInCourseName',
  size: 'classInCourseSize',
  grade_level: 'classInCourseGradeLevel',
  start_year: 'classInCourseStartYear',
  end_year: 'classInCourseEndYear',
  date_range: 'classInCourseStartYear',
}

const toValidation = (result) => (
  result.error ? { message: result.error, field: result.field } : null
)

const ClassInCourseForm = ({ initialData, onSubmit, isLoading, onCancel }) => {
  const [formData, setFormData] = useState(() => createClassDraft(initialData))
  const [validation, setValidation] = useState(null)

  const isInvalid = (field) => validation?.field === field
    || (validation?.field === 'date_range' && (field === 'start_year' || field === 'end_year'))

  const inputProps = (field) => ({
    'aria-invalid': isInvalid(field) || undefined,
    'aria-describedby': isInvalid(field) ? FEEDBACK_ID : undefined,
  })

  const focusField = (field) => {
    document.getElementById(FIELD_IDS[field])?.focus()
  }

  const fieldFeedback = (field) => (
    validation?.field === field
      ? <CFormFeedback id={FEEDBACK_ID} invalid className="d-block" role="alert">{validation.message}</CFormFeedback>
      : null
  )

  const handleChange = (e) => {
    const { name, value } = e.target
    const next = { ...formData, [name]: value }
    setFormData(next)
    if (validation) setValidation(toValidation(validateClassDraft(next)))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    const result = validateClassDraft(formData)
    const nextValidation = toValidation(result)
    setValidation(nextValidation)
    if (nextValidation) {
      focusField(nextValidation.field)
      return
    }
    onSubmit(result.value)
  }

  let submitLabel = 'Criar Turma'
  if (isLoading) submitLabel = 'A gravar...'
  else if (initialData) submitLabel = 'Atualizar Turma'

  return (
    <CForm onSubmit={handleSubmit}>
      <CRow className="g-3">
        <CCol md={8}>
          <CFormInput
            id={FIELD_IDS.name}
            type="text"
            label="Nome da Turma"
            name="name"
            value={formData.name}
            onChange={handleChange}
            required
            placeholder="Ex: TGPSI 10A"
            {...inputProps('name')}
          />
          {fieldFeedback('name')}
        </CCol>

        <CCol md={4}>
          <CFormInput
            id={FIELD_IDS.size}
            type="number"
            label="Nº Alunos"
            name="size"
            value={formData.size}
            onChange={handleChange}
            min="1"
            max="100"
            required
            {...inputProps('size')}
          />
          {fieldFeedback('size')}
        </CCol>

        <CCol md={4}>
          <CFormInput
            id={FIELD_IDS.grade_level}
            type="number"
            label="Ano (10-12)"
            name="grade_level"
            value={formData.grade_level}
            onChange={handleChange}
            min="10"
            max="12"
            required
            {...inputProps('grade_level')}
          />
          {fieldFeedback('grade_level')}
        </CCol>

        <CCol md={4}>
          <CFormInput
            id={FIELD_IDS.start_year}
            type="number"
            label="Início"
            name="start_year"
            value={formData.start_year}
            onChange={handleChange}
            min="2000"
            required
            {...inputProps('start_year')}
          />
          {fieldFeedback('start_year')}
        </CCol>

        <CCol md={4}>
          <CFormInput
            id={FIELD_IDS.end_year}
            type="number"
            label="Fim"
            name="end_year"
            value={formData.end_year}
            onChange={handleChange}
            min="2001"
            required
            {...inputProps('end_year')}
          />
          {fieldFeedback('end_year')}
        </CCol>
      </CRow>

      {fieldFeedback('date_range')}

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
