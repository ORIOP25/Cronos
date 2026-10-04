import { useState } from 'react'
import {
  CButton,
  CCol,
  CForm,
  CFormFeedback,
  CFormInput,
  CModalFooter,
  CRow,
} from '@coreui/react'
import { createClassDraft, validateClassDraft } from '../../utils/classDraft'

const COURSE_FEEDBACK_ID = 'courseFormFeedback'
const CLASS_FEEDBACK_ID = 'courseClassValidation'
const COURSE_FIELDS = { name: 'course-name', abbreviation: 'course-abbreviation' }
const CLASS_FIELDS = {
  name: 'course-class-name',
  size: 'course-class-size',
  grade_level: 'course-class-grade',
  start_year: 'course-class-start',
  end_year: 'course-class-end',
}
const CLASS_ERROR_FIELDS = {
  name: ['name'],
  size: ['size'],
  grade_level: ['grade_level'],
  start_year: ['start_year'],
  end_year: ['end_year'],
  date_range: ['start_year', 'end_year'],
}

const validateCourseFields = (course) => {
  if (!course.name.trim()) return { message: 'Nome do curso é obrigatório.', field: 'name' }
  if (course.abbreviation.trim().length < 2) return { message: 'A sigla deve ter pelo menos 2 caracteres.', field: 'abbreviation' }
  return null
}

const toClassError = (result) => (
  result.error ? { message: result.error, field: result.field } : null
)

const CourseForm = ({ onSubmit, isLoading, onCancel }) => {
  const [course, setCourse] = useState({ name: '', abbreviation: '', classes_config: [] })
  const [classDraft, setClassDraft] = useState(createClassDraft)
  const [classDraftChanged, setClassDraftChanged] = useState(false)
  const [formError, setFormError] = useState(null)
  const [classError, setClassError] = useState(null)

  const updateCourse = (field, value) => {
    const next = { ...course, [field]: value }
    setCourse(next)
    if (formError && formError.field === field) {
      const nextError = validateCourseFields(next)
      setFormError(nextError?.field === formError.field ? nextError : null)
    }
  }

  const updateClass = (field, value) => {
    setClassDraftChanged(true)
    const next = { ...classDraft, [field]: value }
    setClassDraft(next)
    if (classError && CLASS_ERROR_FIELDS[classError.field]?.includes(field)) {
      setClassError(toClassError(validateClassDraft(next, course.classes_config)))
    }
  }

  const focusInvalidClassField = (field) => {
    document.getElementById(CLASS_FIELDS[field] ?? CLASS_FIELDS.start_year)?.focus()
  }

  const addClass = () => {
    const result = validateClassDraft(classDraft, course.classes_config)
    const nextError = toClassError(result)
    setClassError(nextError)
    if (nextError) {
      focusInvalidClassField(nextError.field)
      return
    }
    setCourse((current) => ({
      ...current,
      classes_config: [...current.classes_config, result.value],
    }))
    setClassDraft(createClassDraft())
    setClassDraftChanged(false)
  }

  const submit = (event) => {
    event.preventDefault()
    if (isLoading) return
    const nextError = validateCourseFields(course)
    setFormError(nextError)
    if (nextError) {
      document.getElementById(COURSE_FIELDS[nextError.field])?.focus()
      return
    }
    const classes = [...course.classes_config]
    if (classDraftChanged) {
      const result = validateClassDraft(classDraft, classes)
      const classValidationError = toClassError(result)
      setClassError(classValidationError)
      if (classValidationError) {
        focusInvalidClassField(classValidationError.field)
        return
      }
      classes.push(result.value)
    }
    onSubmit({ name: course.name.trim(), abbreviation: course.abbreviation.trim(), classes_config: classes })
  }

  const isClassInvalid = (field) => classError?.field === field
    || (classError?.field === 'date_range' && (field === 'start_year' || field === 'end_year'))

  const classInputProps = (field) => ({
    invalid: isClassInvalid(field) || undefined,
    'aria-invalid': isClassInvalid(field) || undefined,
    'aria-describedby': isClassInvalid(field) ? CLASS_FEEDBACK_ID : undefined,
  })

  const classFeedback = (field) => (
    classError?.field === field
      ? <CFormFeedback id={CLASS_FEEDBACK_ID} invalid className="d-block" role="alert">{classError.message}</CFormFeedback>
      : null
  )

  return (
    <CForm onSubmit={submit} noValidate>
      <fieldset className="mb-4">
        <legend className="h6 mb-3">Dados gerais</legend>
        <CRow className="g-3">
          <CCol md={8}>
            <CFormInput
              id={COURSE_FIELDS.name}
              label="Nome do Curso"
              value={course.name}
              onChange={(event) => updateCourse('name', event.target.value)}
              required
              invalid={formError?.field === 'name' || undefined}
              aria-invalid={formError?.field === 'name' || undefined}
              aria-describedby={formError?.field === 'name' ? COURSE_FEEDBACK_ID : undefined}
            />
            {formError?.field === 'name' && (
              <CFormFeedback id={COURSE_FEEDBACK_ID} invalid className="d-block" role="alert">{formError.message}</CFormFeedback>
            )}
          </CCol>
          <CCol md={4}>
            <CFormInput
              id={COURSE_FIELDS.abbreviation}
              label="Sigla"
              value={course.abbreviation}
              maxLength={10}
              onChange={(event) => updateCourse('abbreviation', event.target.value)}
              required
              invalid={formError?.field === 'abbreviation' || undefined}
              aria-invalid={formError?.field === 'abbreviation' || undefined}
              aria-describedby={formError?.field === 'abbreviation' ? COURSE_FEEDBACK_ID : undefined}
            />
            {formError?.field === 'abbreviation' && (
              <CFormFeedback id={COURSE_FEEDBACK_ID} invalid className="d-block" role="alert">{formError.message}</CFormFeedback>
            )}
          </CCol>
        </CRow>
      </fieldset>

      <fieldset>
        <legend className="h6 mb-3">Turmas iniciais</legend>
        <p className="small text-muted">A turma preenchida também será incluída ao criar o curso.</p>
        <CRow className="g-2 align-items-end">
          <CCol md={4}>
            <CFormInput id={CLASS_FIELDS.name} label="Nome Turma" value={classDraft.name} onChange={(event) => updateClass('name', event.target.value)} {...classInputProps('name')} />
            {classFeedback('name')}
          </CCol>
          <CCol md={2}>
            <CFormInput id={CLASS_FIELDS.grade_level} label="Ano (10-12)" type="number" min={10} max={12} value={classDraft.grade_level} onChange={(event) => updateClass('grade_level', event.target.value)} {...classInputProps('grade_level')} />
            {classFeedback('grade_level')}
          </CCol>
          <CCol md={2}>
            <CFormInput id={CLASS_FIELDS.start_year} label="Ano de início" type="number" value={classDraft.start_year} onChange={(event) => updateClass('start_year', event.target.value)} {...classInputProps('start_year')} />
            {classFeedback('start_year')}
          </CCol>
          <CCol md={2}>
            <CFormInput id={CLASS_FIELDS.end_year} label="Ano de fim" type="number" value={classDraft.end_year} onChange={(event) => updateClass('end_year', event.target.value)} {...classInputProps('end_year')} />
            {classFeedback('end_year')}
          </CCol>
          <CCol md={2}>
            <CFormInput id={CLASS_FIELDS.size} label="Alunos" type="number" min={1} max={100} value={classDraft.size} onChange={(event) => updateClass('size', event.target.value)} {...classInputProps('size')} />
            {classFeedback('size')}
          </CCol>
          <CCol xs={12}><CButton type="button" color="secondary" variant="outline" onClick={addClass}>Adicionar turma</CButton></CCol>
        </CRow>
        {classFeedback('date_range')}

        <div className="mt-3 d-grid gap-2">
          {course.classes_config.map((item, index) => (
            <div key={`${item.name}-${index}`} className="d-flex justify-content-between align-items-center border rounded p-2">
              <span>{item.name} · {item.grade_level}.º ano · {item.size} alunos</span>
              <CButton
                type="button"
                color="danger"
                variant="ghost"
                size="sm"
                aria-label={`Remover ${item.name}`}
                onClick={() => setCourse((current) => ({
                  ...current,
                  classes_config: current.classes_config.filter((_, itemIndex) => itemIndex !== index),
                }))}
              >Remover</CButton>
            </div>
          ))}
        </div>
      </fieldset>

      <CModalFooter className="px-0 mt-4 border-0 pb-0">
        <CButton type="button" color="secondary" variant="ghost" onClick={onCancel}>Cancelar</CButton>
        <CButton type="submit" color="primary" disabled={isLoading}>
          {isLoading ? 'A gravar...' : 'Criar Curso'}
        </CButton>
      </CModalFooter>
    </CForm>
  )
}

export default CourseForm
