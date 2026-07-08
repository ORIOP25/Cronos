import React, { useState, useMemo, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import PropTypes from 'prop-types'
import {
  CCard, CCardBody, CCardHeader, CCol, CRow, CButton, CAlert,
  CBadge, CSpinner, CFormInput,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import {
  cilArrowLeft, cilPencil, cilSave, cilX, cilTrash,
  cilBookmark, cilPeople, cilChevronRight, cilPlus,
} from '@coreui/icons'
import GenericModalForm from '../components/GenericModalForm'
import ClassInCourseForm from '../components/Forms/ClassInCourseForm'
import ConfirmationModal from '../components/ConfirmationModal'
import { getApiErrorMessage } from '../utils/apiErrors'

import {
  useCourseDetails,
  useUpdateCourse,
  useDeleteCourse,
  useCreateCourseClass,
  useUpdateCourseClass,
  useDeleteCourseClass,
} from '../hooks/useSchoolData'
import Breadcrumbs from '../components/Breadcrumbs'

// ==========================================
//  HELPER: Card de turma (grade_level agrupado)
// ==========================================
const ClassCard = ({ cls, onNavigate, onEdit, onDelete }) => {
  const yearLabel = `${cls.start_year}/${cls.end_year}`
  const gradeLabels = { 10: '10.º ano', 11: '11.º ano', 12: '12.º ano' }

  return (
    <CCard
      className="border h-100 shadow-sm class-card"
      style={{ cursor: 'pointer', transition: 'box-shadow 0.2s, transform 0.15s' }}
      onClick={() => onNavigate(cls)}
      onMouseEnter={(e) => {
      e.currentTarget.style.boxShadow = '0 4px 15px var(--rs-card-shadow-hover)'
        e.currentTarget.style.transform = 'translateY(-2px)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.boxShadow = ''
        e.currentTarget.style.transform = ''
      }}
    >
      <CCardBody className="d-flex flex-column">
        <div className="d-flex justify-content-between align-items-start mb-2">
          <div>
            <h6 className="mb-0 fw-bold">{cls.name}</h6>
            <small className="text-muted">{gradeLabels[cls.grade_level] || `${cls.grade_level}.º ano`}</small>
          </div>
          <CBadge color="primary" shape="rounded-pill">{yearLabel}</CBadge>
        </div>
        <div className="d-flex align-items-center gap-2 mt-auto text-muted" style={{ fontSize: '0.85rem' }}>
          <CIcon icon={cilPeople} size="sm" />
          <span>{cls.size} alunos</span>
          <div className="ms-auto d-flex align-items-center gap-1">
            <CButton
              size="sm"
              color="light"
              className="d-flex align-items-center gap-1 text-primary"
              onClick={(e) => {
                e.stopPropagation()
                onEdit(cls)
              }}
            >
              <CIcon icon={cilPencil} size="sm" />
            </CButton>
            <CButton
              size="sm"
              color="danger"
              variant="ghost"
              onClick={(e) => {
                e.stopPropagation()
                onDelete(cls)
              }}
            >
              <CIcon icon={cilTrash} size="sm" />
            </CButton>
            <CIcon icon={cilChevronRight} size="sm" />
          </div>
        </div>
      </CCardBody>
    </CCard>
  )
}

// ==========================================
//  COMPONENT PRINCIPAL: CourseDetails
// ==========================================
const CourseDetails = () => {
  const { id } = useParams()
  const navigate = useNavigate()
  const courseId = Number(id)

  // --- DATA ---
  const { data: course, isLoading, error } = useCourseDetails(courseId)
  const updateCourse = useUpdateCourse()
  const deleteCourse = useDeleteCourse()
  const createCourseClass = useCreateCourseClass()
  const updateCourseClass = useUpdateCourseClass()
  const deleteCourseClass = useDeleteCourseClass()

  // --- STATE: Edição do header ---
  const [editingHeader, setEditingHeader] = useState(false)
  const [headerForm, setHeaderForm] = useState({ name: '', abbreviation: '' })
  const [classModalVisible, setClassModalVisible] = useState(false)
  const [selectedClass, setSelectedClass] = useState(null)
  const [deleteConfirmation, setDeleteConfirmation] = useState(null)

  // --- MEMOIZED: Turmas agrupadas por grade_level ---
  // eslint-disable-next-line react-hooks/preserve-manual-memoization
  const classGroups = useMemo(() => {
    if (!course?.classes) return {}
    const groups = {}
    for (const cls of course.classes) {
      const grade = cls.grade_level || 0
      if (!groups[grade]) groups[grade] = []
      groups[grade].push(cls)
    }
    // Ordenar turmas dentro de cada grupo por start_year (mais recente primeiro)
    for (const grade of Object.keys(groups)) {
      groups[grade].sort((a, b) => b.start_year - a.start_year)
    }
    return groups
    }, [course?.classes])

  const sortedGrades = useMemo(
    () => Object.keys(classGroups).map(Number).sort((a, b) => a - b),
    [classGroups]
  )

  // ==========================================
  //  HANDLERS
  // ==========================================

  const startEditHeader = useCallback(() => {
    setHeaderForm({ name: course.name, abbreviation: course.abbreviation })
    setEditingHeader(true)
  }, [course])

  const cancelEditHeader = () => setEditingHeader(false)

  const saveHeader = () => {
    // Validação básica client-side
    const trimName = headerForm.name.trim()
    const trimAbbr = headerForm.abbreviation.trim()
    if (!trimName || !trimAbbr) return

    updateCourse.mutate(
      { courseId, data: { name: trimName, abbreviation: trimAbbr } },
      { onSuccess: () => setEditingHeader(false) }
    )
  }

  const handleDeleteCourse = () => {
    setDeleteConfirmation({ type: 'course' })
  }

  const handleClassClick = (cls) => {
    navigate(`/courses/${courseId}/classes/${cls.id}`)
  }

  const handleOpenCreateClass = () => {
    setSelectedClass(null)
    setClassModalVisible(true)
  }

  const handleOpenEditClass = (cls) => {
    setSelectedClass(cls)
    setClassModalVisible(true)
  }

  const handleSubmitClass = (formData) => {
    if (selectedClass) {
      updateCourseClass.mutate(
        { courseId, classId: selectedClass.id, data: formData },
        {
          onSuccess: () => {
            setClassModalVisible(false)
            setSelectedClass(null)
          }
        }
      )
      return
    }

    createCourseClass.mutate(
      { courseId, data: formData },
      {
        onSuccess: () => {
          setClassModalVisible(false)
        }
      }
    )
  }

  const handleDeleteClass = (cls) => {
    setDeleteConfirmation({ type: 'class', classData: cls })
  }

  const handleConfirmDelete = () => {
    if (deleteConfirmation?.type === 'course') {
      deleteCourse.mutate(courseId, {
        onSuccess: () => { navigate('/courses') },
        onSettled: () => setDeleteConfirmation(null),
      })
      return
    }

    if (deleteConfirmation?.type === 'class') {
      deleteCourseClass.mutate(
        { courseId, classId: deleteConfirmation.classData.id },
        { onSettled: () => setDeleteConfirmation(null) }
      )
    }
  }

  const deleteMessage = deleteConfirmation?.type === 'class'
    ? `Apagar a turma ${deleteConfirmation.classData.name}? Esta ação elimina aulas, agendamentos e substituições associados.`
    : 'Apagar este curso? Esta ação é irreversível e pode falhar se houver turmas.'

  // ==========================================
  //  RENDER: Loading / Error
  // ==========================================

  if (isLoading) {
    return (
      <div className="p-4 text-center">
        <CSpinner color="primary" />
        <p className="text-muted mt-2">A carregar curso...</p>
      </div>
    )
  }

  if (error || !course) {
    return (
      <div className="p-4">
        <CAlert color="danger">
          <strong>Erro:</strong> {getApiErrorMessage(error, 'Curso não encontrado.')}
        </CAlert>
        <CButton color="light" onClick={() => navigate('/courses')}>
          <CIcon icon={cilArrowLeft} className="me-1" /> Voltar aos Cursos
        </CButton>
      </div>
    )
  }

  // ==========================================
  //  RENDER: Page
  // ==========================================

  return (
    <div className="p-4">
      <Breadcrumbs items={[
        { label: 'Cursos', to: '/courses' },
        { label: course?.name || `Curso #${courseId}` },
      ]} />

      {/* ---- ALERTAS DE MUTAÇÕES ---- */}
      {updateCourse.isError && (
        <CAlert color="danger" dismissible onClose={() => updateCourse.reset()}>
          <strong>Erro ao atualizar:</strong>{' '}
          {getApiErrorMessage(updateCourse.error)}
        </CAlert>
      )}
      {deleteCourse.isError && (
        <CAlert color="danger" dismissible onClose={() => deleteCourse.reset()}>
          <strong>Erro ao apagar:</strong>{' '}
          {getApiErrorMessage(deleteCourse.error, 'Não é possível apagar este curso.')}
        </CAlert>
      )}
      {(createCourseClass.isError || updateCourseClass.isError || deleteCourseClass.isError) && (
        <CAlert
          color="danger"
          dismissible
          onClose={() => {
            createCourseClass.reset()
            updateCourseClass.reset()
            deleteCourseClass.reset()
          }}
        >
          <strong>Erro ao gerir turma:</strong>{' '}
          {getApiErrorMessage(
            createCourseClass.error || updateCourseClass.error || deleteCourseClass.error
          )}
        </CAlert>
      )}

      {/* ==== HEADER DO CURSO ==== */}
      <CCard className="mb-4 border-0 shadow-sm">
        <CCardBody>
          {editingHeader ? (
            /* --- MODO EDIÇÃO --- */
            <div>
              <CRow className="g-3 align-items-end">
                <CCol md={6}>
                  <label htmlFor="courseNameInput" className="form-label fw-semibold">Nome do Curso</label>
                  <CFormInput
                    id="courseNameInput"
                    value={headerForm.name}
                    onChange={(e) => setHeaderForm(prev => ({ ...prev, name: e.target.value }))}
                    placeholder="Nome completo do curso"
                    autoFocus
                  />
                </CCol>
                <CCol md={3}>
                  <label htmlFor="courseAbbreviationInput" className="form-label fw-semibold">Sigla</label>
                  <CFormInput
                    id="courseAbbreviationInput"
                    value={headerForm.abbreviation}
                    onChange={(e) => setHeaderForm(prev => ({ ...prev, abbreviation: e.target.value }))}
                    placeholder="Ex: TGEI"
                    maxLength={10}
                  />
                </CCol>
                <CCol md={3} className="d-flex gap-2">
                  <CButton
                    color="primary"
                    onClick={saveHeader}
                    disabled={updateCourse.isPending}
                  >
                    {updateCourse.isPending ? <CSpinner size="sm" /> : <CIcon icon={cilSave} className="me-1" />}
                    Guardar
                  </CButton>
                  <CButton color="light" onClick={cancelEditHeader} disabled={updateCourse.isPending}>
                    <CIcon icon={cilX} />
                  </CButton>
                </CCol>
              </CRow>
            </div>
          ) : (
            /* --- MODO VISUALIZAÇÃO --- */
            <div className="d-flex justify-content-between align-items-center">
              <div>
                <div className="d-flex align-items-center gap-2 mb-1">
                  <CIcon icon={cilBookmark} className="text-primary" />
                  <h3 className="mb-0 fw-bold">{course.name}</h3>
                  <CBadge color="primary" shape="rounded-pill" style={{ fontSize: '0.9rem' }}>
                    {course.abbreviation}
                  </CBadge>
                </div>
                <small className="text-muted">
                  {course.subjects?.length || 0} disciplinas · {course.classes?.length || 0} turmas
                </small>
              </div>
              <div className="d-flex gap-2">
                <CButton color="light" size="sm" className="d-flex align-items-center gap-1 text-primary" onClick={startEditHeader} title="Editar nome e sigla">
                  <CIcon icon={cilPencil} size="sm" />
                  Editar
                </CButton>
                <CButton color="danger" variant="ghost" size="sm" className="d-flex align-items-center" onClick={handleDeleteCourse} title="Apagar curso">
                  <CIcon icon={cilTrash} size="sm" />
                </CButton>
              </div>
            </div>
          )}
        </CCardBody>
      </CCard>

      <CRow className="g-4">
        {/* ==== TURMAS ==== */}
        <CCol lg={12}>
          <CCard className="border-0 shadow-sm h-100">
            <CCardHeader className="bg-transparent d-flex align-items-center gap-2">
              <CIcon icon={cilPeople} className="text-success" />
              <strong>Turmas</strong>
              <CBadge color="success" shape="rounded-pill">{course.classes?.length || 0}</CBadge>
              <CButton
                color="primary"
                size="sm"
                className="ms-auto d-flex align-items-center gap-1"
                onClick={handleOpenCreateClass}
              >
                <CIcon icon={cilPlus} size="sm" />
                Nova Turma
              </CButton>
            </CCardHeader>
            <CCardBody>
              {(course.classes || []).length === 0 ? (
                <div className="text-muted text-center mb-0">
                  <p className="mb-3">Nenhuma turma criada para este curso.</p>
                  <CButton color="primary" variant="outline" onClick={handleOpenCreateClass}>
                    <CIcon icon={cilPlus} className="me-1" /> Criar primeira turma
                  </CButton>
                </div>
              ) : (
                sortedGrades.map(grade => (
                  <div key={grade} className="mb-4">
                    <h6 className="text-muted fw-bold mb-3 text-uppercase" style={{ fontSize: '0.8rem', letterSpacing: '0.5px' }}>
                      {grade}.º Ano
                    </h6>
                    <CRow className="g-3">
                      {classGroups[grade].map(cls => (
                        <CCol sm={6} md={4} key={cls.id}>
                          <ClassCard
                            cls={cls}
                            onNavigate={handleClassClick}
                            onEdit={handleOpenEditClass}
                            onDelete={handleDeleteClass}
                          />
                        </CCol>
                      ))}
                    </CRow>
                  </div>
                ))
              )}
            </CCardBody>
          </CCard>
        </CCol>
      </CRow>

      <GenericModalForm
        visible={classModalVisible}
        onClose={() => {
          setClassModalVisible(false)
          setSelectedClass(null)
          createCourseClass.reset()
          updateCourseClass.reset()
        }}
        title="Turma"
        FormComponent={ClassInCourseForm}
        initialData={selectedClass}
        onSubmit={handleSubmitClass}
        isLoading={createCourseClass.isPending || updateCourseClass.isPending}
        error={createCourseClass.error || updateCourseClass.error}
      />
      <ConfirmationModal
        visible={Boolean(deleteConfirmation)}
        onClose={() => setDeleteConfirmation(null)}
        onConfirm={handleConfirmDelete}
        title={deleteConfirmation?.type === 'class' ? 'Confirmar remoção da turma' : 'Confirmar remoção do curso'}
        message={deleteMessage}
        confirmText="Remover"
        isLoading={deleteCourse.isPending || deleteCourseClass.isPending}
        variant="danger"
      />
    </div>
  )
}

export default CourseDetails

ClassCard.propTypes = {
  cls: PropTypes.object.isRequired,
  onNavigate: PropTypes.func.isRequired,
  onEdit: PropTypes.func.isRequired,
  onDelete: PropTypes.func.isRequired,
}
