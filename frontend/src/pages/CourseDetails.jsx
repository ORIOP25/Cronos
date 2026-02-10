import React, { useState, useMemo, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  CCard, CCardBody, CCardHeader, CCol, CRow, CButton, CAlert,
  CBadge, CSpinner, CFormInput,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import {
  cilArrowLeft, cilPencil, cilSave, cilX, cilTrash,
  cilBookmark, cilBook, cilPeople, cilChevronRight,
} from '@coreui/icons'

import {
  useCourseDetails,
  useUpdateCourse,
  useDeleteCourse,
  useSubjects,
} from '../hooks/useSchoolData'

// ==========================================
//  HELPER: Badge de tipo de sala
// ==========================================
const RoomBadge = ({ type }) => {
  const config = {
    gym: { color: 'warning', label: 'Ginásio' },
    lab: { color: 'info', label: 'Laboratório' },
    art: { color: 'danger', label: 'Artes' },
    normal: { color: 'light', label: 'Normal', textClass: 'text-dark' },
  }
  const c = config[type] || config.normal
  return <CBadge color={c.color} shape="rounded-pill" className={c.textClass || ''}>{c.label}</CBadge>
}

// ==========================================
//  HELPER: Card de turma (grade_level agrupado)
// ==========================================
const ClassCard = ({ cls, courseId, onNavigate }) => {
  const yearLabel = `${cls.start_year}/${cls.end_year}`
  const gradeLabels = { 10: '10.º ano', 11: '11.º ano', 12: '12.º ano' }

  return (
    <CCard
      className="border h-100 shadow-sm class-card"
      style={{ cursor: 'pointer', transition: 'box-shadow 0.2s, transform 0.15s' }}
      onClick={() => onNavigate(cls)}
      onMouseEnter={(e) => {
        e.currentTarget.style.boxShadow = '0 4px 15px rgba(0,0,0,0.15)'
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
          <CIcon icon={cilChevronRight} size="sm" className="ms-auto" />
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
  const { data: allSubjects } = useSubjects()
  const updateCourse = useUpdateCourse()
  const deleteCourse = useDeleteCourse()

  // --- STATE: Edição do header ---
  const [editingHeader, setEditingHeader] = useState(false)
  const [headerForm, setHeaderForm] = useState({ name: '', abbreviation: '' })

  // --- STATE: Edição de disciplinas ---
  const [editingSubjects, setEditingSubjects] = useState(false)
  const [selectedSubjectIds, setSelectedSubjectIds] = useState([])

  // --- MEMOIZED: Turmas agrupadas por grade_level ---
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

  // --- MEMOIZED: Disciplinas disponíveis (não associadas ao curso) ---
  const availableSubjects = useMemo(() => {
    if (!allSubjects || !course) return []
    const courseSubjectIds = new Set((course.subjects || []).map(s => s.id))
    return allSubjects.filter(s => !courseSubjectIds.has(s.id))
  }, [allSubjects, course])

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

  const startEditSubjects = useCallback(() => {
    setSelectedSubjectIds((course.subjects || []).map(s => s.id))
    setEditingSubjects(true)
  }, [course])

  const cancelEditSubjects = () => setEditingSubjects(false)

  const toggleSubject = (subjectId) => {
    setSelectedSubjectIds(prev =>
      prev.includes(subjectId)
        ? prev.filter(id => id !== subjectId)
        : [...prev, subjectId]
    )
  }

  const saveSubjects = () => {
    updateCourse.mutate(
      { courseId, data: { subject_ids: selectedSubjectIds } },
      { onSuccess: () => setEditingSubjects(false) }
    )
  }

  const handleDeleteCourse = () => {
    if (window.confirm('Apagar este curso? Esta ação é irreversível e pode falhar se houver turmas.')) {
      deleteCourse.mutate(courseId, {
        onSuccess: () => navigate('/courses')
      })
    }
  }

  const handleClassClick = (cls) => {
    navigate(`/courses/${courseId}/classes/${cls.id}`)
  }

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
          <strong>Erro:</strong> {error?.response?.data?.detail || 'Curso não encontrado.'}
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
      {/* ---- BREADCRUMB + BACK ---- */}
      <div className="mb-3">
        <Link to="/courses" className="text-decoration-none text-muted d-inline-flex align-items-center gap-1" style={{ fontSize: '0.9rem' }}>
          <CIcon icon={cilArrowLeft} size="sm" />
          Cursos
        </Link>
      </div>

      {/* ---- ALERTAS DE MUTAÇÕES ---- */}
      {updateCourse.isError && (
        <CAlert color="danger" dismissible onClose={() => updateCourse.reset()}>
          <strong>Erro ao atualizar:</strong>{' '}
          {updateCourse.error?.response?.data?.detail || 'Ocorreu um erro inesperado.'}
        </CAlert>
      )}
      {deleteCourse.isError && (
        <CAlert color="danger" dismissible onClose={() => deleteCourse.reset()}>
          <strong>Erro ao apagar:</strong>{' '}
          {deleteCourse.error?.response?.data?.detail || 'Não é possível apagar este curso.'}
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
                  <label className="form-label fw-semibold">Nome do Curso</label>
                  <CFormInput
                    value={headerForm.name}
                    onChange={(e) => setHeaderForm(prev => ({ ...prev, name: e.target.value }))}
                    placeholder="Nome completo do curso"
                    autoFocus
                  />
                </CCol>
                <CCol md={3}>
                  <label className="form-label fw-semibold">Sigla</label>
                  <CFormInput
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
                <CButton color="light" size="sm" onClick={startEditHeader} title="Editar nome e sigla">
                  <CIcon icon={cilPencil} className="me-1" />
                  Editar
                </CButton>
                <CButton color="danger" variant="ghost" size="sm" onClick={handleDeleteCourse} title="Apagar curso">
                  <CIcon icon={cilTrash} />
                </CButton>
              </div>
            </div>
          )}
        </CCardBody>
      </CCard>

      <CRow className="g-4">
        {/* ==== DISCIPLINAS ==== */}
        <CCol lg={5}>
          <CCard className="border-0 shadow-sm h-100">
            <CCardHeader className="bg-transparent d-flex justify-content-between align-items-center">
              <div className="d-flex align-items-center gap-2">
                <CIcon icon={cilBook} className="text-info" />
                <strong>Disciplinas</strong>
                <CBadge color="info" shape="rounded-pill">{course.subjects?.length || 0}</CBadge>
              </div>
              {!editingSubjects ? (
                <CButton color="light" size="sm" onClick={startEditSubjects}>
                  <CIcon icon={cilPencil} size="sm" className="me-1" />
                  Gerir
                </CButton>
              ) : (
                <div className="d-flex gap-1">
                  <CButton color="primary" size="sm" onClick={saveSubjects} disabled={updateCourse.isPending}>
                    {updateCourse.isPending ? <CSpinner size="sm" /> : <CIcon icon={cilSave} size="sm" className="me-1" />}
                    Guardar
                  </CButton>
                  <CButton color="light" size="sm" onClick={cancelEditSubjects}>
                    <CIcon icon={cilX} size="sm" />
                  </CButton>
                </div>
              )}
            </CCardHeader>
            <CCardBody style={{ maxHeight: '500px', overflowY: 'auto' }}>
              {editingSubjects ? (
                /* --- MODO EDIÇÃO: Checkboxes --- */
                <div>
                  {/* Disciplinas já associadas */}
                  {(allSubjects || [])
                    .filter(s => selectedSubjectIds.includes(s.id))
                    .sort((a, b) => a.name.localeCompare(b.name))
                    .map(s => (
                      <div
                        key={s.id}
                        className="d-flex align-items-center justify-content-between p-2 mb-1 rounded"
                        style={{ backgroundColor: '#e8f5e9', cursor: 'pointer' }}
                        onClick={() => toggleSubject(s.id)}
                      >
                        <div className="d-flex align-items-center gap-2">
                          <input type="checkbox" checked readOnly style={{ pointerEvents: 'none' }} />
                          <span className="fw-medium">{s.name}</span>
                        </div>
                        <RoomBadge type={s.required_room_type} />
                      </div>
                    ))}

                  {/* Separador */}
                  {availableSubjects.length > 0 && selectedSubjectIds.length > 0 && (
                    <hr className="my-2" />
                  )}

                  {/* Disciplinas disponíveis */}
                  {availableSubjects
                    .filter(s => !selectedSubjectIds.includes(s.id))
                    .sort((a, b) => a.name.localeCompare(b.name))
                    .map(s => (
                      <div
                        key={s.id}
                        className="d-flex align-items-center justify-content-between p-2 mb-1 rounded"
                        style={{ cursor: 'pointer', opacity: 0.7 }}
                        onClick={() => toggleSubject(s.id)}
                      >
                        <div className="d-flex align-items-center gap-2">
                          <input type="checkbox" checked={false} readOnly style={{ pointerEvents: 'none' }} />
                          <span>{s.name}</span>
                        </div>
                        <RoomBadge type={s.required_room_type} />
                      </div>
                    ))}

                  {(allSubjects || []).length === 0 && (
                    <p className="text-muted text-center mb-0">
                      Nenhuma disciplina registada. Crie disciplinas primeiro.
                    </p>
                  )}
                </div>
              ) : (
                /* --- MODO VISUALIZAÇÃO: Lista simples --- */
                <div>
                  {(course.subjects || []).length === 0 ? (
                    <p className="text-muted text-center mb-0">
                      Nenhuma disciplina associada.
                    </p>
                  ) : (
                    course.subjects
                      .sort((a, b) => a.name.localeCompare(b.name))
                      .map(s => (
                        <div
                          key={s.id}
                          className="d-flex align-items-center justify-content-between p-2 mb-1 border-bottom"
                        >
                          <span>{s.name}</span>
                          <RoomBadge type={s.required_room_type} />
                        </div>
                      ))
                  )}
                </div>
              )}
            </CCardBody>
          </CCard>
        </CCol>

        {/* ==== TURMAS ==== */}
        <CCol lg={7}>
          <CCard className="border-0 shadow-sm h-100">
            <CCardHeader className="bg-transparent d-flex align-items-center gap-2">
              <CIcon icon={cilPeople} className="text-success" />
              <strong>Turmas</strong>
              <CBadge color="success" shape="rounded-pill">{course.classes?.length || 0}</CBadge>
            </CCardHeader>
            <CCardBody>
              {(course.classes || []).length === 0 ? (
                <p className="text-muted text-center mb-0">
                  Nenhuma turma criada. As turmas são geradas automaticamente na criação do curso.
                </p>
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
                            courseId={courseId}
                            onNavigate={handleClassClick}
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
    </div>
  )
}

export default CourseDetails
