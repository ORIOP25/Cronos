import { useState } from 'react'
import {
  CAlert,
  CButton,
  CCol,
  CForm,
  CFormInput,
  CModalFooter,
  CRow,
} from '@coreui/react'
import { createClassDraft, validateClassDraft } from '../../utils/classDraft'

const CourseForm = ({ onSubmit, isLoading, onCancel }) => {
  const [course, setCourse] = useState({ name: '', abbreviation: '', classes_config: [] })
  const [classDraft, setClassDraft] = useState(createClassDraft)
  const [formError, setFormError] = useState('')
  const [classError, setClassError] = useState('')

  const updateCourse = (field, value) => {
    setCourse((current) => ({ ...current, [field]: value }))
    setFormError('')
  }

  const updateClass = (field, value) => {
    setClassDraft((current) => ({ ...current, [field]: value }))
    setClassError('')
  }

  const addClass = () => {
    const validation = validateClassDraft(classDraft, course.classes_config)
    if (validation.error) return setClassError(validation.error)
    setCourse((current) => ({
      ...current,
      classes_config: [...current.classes_config, validation.value],
    }))
    setClassDraft(createClassDraft())
  }

  const submit = (event) => {
    event.preventDefault()
    const name = course.name.trim()
    const abbreviation = course.abbreviation.trim()
    if (!name) return setFormError('Nome do curso é obrigatório.')
    if (abbreviation.length < 2) return setFormError('A sigla deve ter pelo menos 2 caracteres.')
    onSubmit({ name, abbreviation, classes_config: course.classes_config })
  }

  return (
    <CForm onSubmit={submit}>
      {formError && <CAlert color="danger">{formError}</CAlert>}

      <fieldset className="mb-4">
        <legend className="h6 mb-3">Dados gerais</legend>
        <CRow className="g-3">
          <CCol md={8}>
            <CFormInput id="course-name" label="Nome do Curso" value={course.name} onChange={(event) => updateCourse('name', event.target.value)} required />
          </CCol>
          <CCol md={4}>
            <CFormInput id="course-abbreviation" label="Sigla" value={course.abbreviation} maxLength={10} onChange={(event) => updateCourse('abbreviation', event.target.value)} required />
          </CCol>
        </CRow>
      </fieldset>

      <fieldset>
        <legend className="h6 mb-3">Turmas iniciais</legend>
        {classError && <CAlert color="danger">{classError}</CAlert>}
        <CRow className="g-2 align-items-end">
          <CCol md={4}><CFormInput id="course-class-name" label="Nome Turma" value={classDraft.name} onChange={(event) => updateClass('name', event.target.value)} /></CCol>
          <CCol md={2}><CFormInput id="course-class-grade" label="Ano (10-12)" type="number" min={10} max={12} value={classDraft.grade_level} onChange={(event) => updateClass('grade_level', event.target.value)} /></CCol>
          <CCol md={2}><CFormInput id="course-class-start" label="Ano de início" type="number" value={classDraft.start_year} onChange={(event) => updateClass('start_year', event.target.value)} /></CCol>
          <CCol md={2}><CFormInput id="course-class-end" label="Ano de fim" type="number" value={classDraft.end_year} onChange={(event) => updateClass('end_year', event.target.value)} /></CCol>
          <CCol md={2}><CFormInput id="course-class-size" label="Alunos" type="number" min={1} max={100} value={classDraft.size} onChange={(event) => updateClass('size', event.target.value)} /></CCol>
          <CCol xs={12}><CButton type="button" color="secondary" variant="outline" onClick={addClass}>Adicionar turma</CButton></CCol>
        </CRow>

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
