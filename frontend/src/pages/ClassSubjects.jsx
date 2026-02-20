import React, { useState, useMemo } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  CCard, CCardBody, CCardHeader, CCol, CRow, CButton, CAlert,
  CBadge, CSpinner, CFormSelect,
  CModal, CModalHeader, CModalTitle,
  CModalBody, CModalFooter,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import {
  cilArrowLeft, cilBook, cilUserPlus, cilTrash, cilPeople,
  cilBookmark, cilCheckCircle, cilWarning,
} from '@coreui/icons'

import {
  useClassSubjects,
  useAvailableSubjects,
  useEligibleTeachers,
  useAddClassSubject,
  useUpdateClassSubjectTeacher,
  useRemoveClassSubject,
} from '../hooks/useSchoolData'

// ==========================================
//  HELPERS
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

const gradeLabels = { 10: '10.º ano', 11: '11.º ano', 12: '12.º ano' }

// ==========================================
//  SUB-COMPONENT: Card de disciplina com dropdown de professor
// ==========================================
const SubjectRow = ({ 
  subject, 
  classId,
  onRemove,
  onTeacherChange,
  isUpdating 
}) => {
  const { data: eligibleTeachers, isLoading: teachersLoading } = useEligibleTeachers(subject.subject_id)
  
  const handleTeacherChange = (e) => {
    const teacherId = e.target.value ? parseInt(e.target.value) : null
    onTeacherChange(subject.subject_id, teacherId)
  }

  return (
    <CCard className="mb-2 border shadow-sm">
      <CCardBody className="py-2 px-3">
        <div className="d-flex justify-content-between align-items-center">
          {/* Info da Disciplina */}
          <div className="d-flex align-items-center gap-2" style={{ minWidth: '180px' }}>
            <CIcon icon={cilBook} className="text-info" size="sm" />
            <span className="fw-medium">{subject.subject_name}</span>
            <RoomBadge type={subject.required_room_type} />
          </div>

          {/* Dropdown de Professor */}
          <div className="d-flex align-items-center gap-2" style={{ flex: 1, maxWidth: '280px' }}>
            {teachersLoading ? (
              <CSpinner size="sm" />
            ) : (
              <CFormSelect
                size="sm"
                value={subject.teacher_id || ''}
                onChange={handleTeacherChange}
                disabled={isUpdating}
                style={{ minWidth: '180px' }}
              >
                <option value="">
                  {eligibleTeachers?.length === 0 
                    ? 'Nenhum professor com competência'
                    : 'Selecionar professor...'
                  }
                </option>
                {(eligibleTeachers || []).map(teacher => (
                  <option key={teacher.id} value={teacher.id}>
                    {teacher.name}
                    {teacher.current_classes_count > 0 && ` (${teacher.current_classes_count} turmas)`}
                  </option>
                ))}
              </CFormSelect>
            )}
            
            {/* Indicador de estado */}
            {subject.teacher_id ? (
              <CIcon icon={cilCheckCircle} className="text-success" title="Professor atribuído" />
            ) : (
              <CIcon icon={cilWarning} className="text-warning" title="Sem professor" />
            )}
          </div>

          {/* Botão Remover */}
          <CButton
            color="danger"
            variant="ghost"
            size="sm"
            onClick={() => onRemove(subject.subject_id)}
            disabled={isUpdating}
            title="Remover disciplina"
          >
            <CIcon icon={cilTrash} />
          </CButton>
        </div>
        
        {/* Info do professor atribuído */}
        {subject.teacher_name && (
          <small className="text-success d-block mt-1 ms-4">
            <CIcon icon={cilCheckCircle} size="sm" className="me-1" />
            {subject.teacher_name}
          </small>
        )}
      </CCardBody>
    </CCard>
  )
}

// ==========================================
//  COMPONENT PRINCIPAL: ClassSubjects
// ==========================================
const ClassSubjects = () => {
  const { courseId, classId } = useParams()
  const navigate = useNavigate()
  const numClassId = Number(classId)
  const numCourseId = Number(courseId)

  // State para modal de adicionar disciplina
  const [showAddModal, setShowAddModal] = useState(false)
  const [selectedSubjectToAdd, setSelectedSubjectToAdd] = useState('')

  // Data hooks
  const { data: classSubjects, isLoading, error } = useClassSubjects(numClassId)
  const { data: availableSubjects, isLoading: availableLoading } = useAvailableSubjects(numClassId)

  // Mutation hooks
  const addSubject = useAddClassSubject()
  const updateTeacher = useUpdateClassSubjectTeacher()
  const removeSubject = useRemoveClassSubject()

  const isUpdating = addSubject.isPending || updateTeacher.isPending || removeSubject.isPending

  // Stats
  const stats = useMemo(() => {
    if (!classSubjects?.subjects) return { total: 0, assigned: 0, pending: 0 }
    const total = classSubjects.subjects.length
    const assigned = classSubjects.subjects.filter(s => s.teacher_id).length
    return { total, assigned, pending: total - assigned }
  }, [classSubjects])

  // Handlers
  const handleAddSubject = () => {
    if (!selectedSubjectToAdd) return
    addSubject.mutate(
      { classId: numClassId, subjectId: parseInt(selectedSubjectToAdd) },
      { onSuccess: () => { setShowAddModal(false); setSelectedSubjectToAdd('') } }
    )
  }

  const handleRemoveSubject = (subjectId) => {
    if (!window.confirm('Remover esta disciplina da turma?')) return
    removeSubject.mutate({ classId: numClassId, subjectId })
  }

  const handleTeacherChange = (subjectId, teacherId) => {
    updateTeacher.mutate({ classId: numClassId, subjectId, teacherId })
  }

  // Loading state
  if (isLoading) {
    return (
      <div className="p-4 text-center">
        <CSpinner color="primary" />
        <p className="text-muted mt-2">A carregar disciplinas...</p>
      </div>
    )
  }

  // Error state
  if (error || !classSubjects) {
    return (
      <div className="p-4">
        <CAlert color="danger">
          <strong>Erro:</strong> {error?.response?.data?.detail || 'Turma não encontrada.'}
        </CAlert>
        <CButton color="light" onClick={() => navigate(`/courses/${numCourseId}`)}>
          <CIcon icon={cilArrowLeft} className="me-1" /> Voltar ao Curso
        </CButton>
      </div>
    )
  }

  return (
    <div className="p-4">
      {/* Breadcrumb */}
      <div className="mb-3 d-flex align-items-center gap-1" style={{ fontSize: '0.9rem' }}>
        <Link to="/courses" className="text-decoration-none text-muted">Cursos</Link>
        <span className="text-muted">/</span>
        <Link to={`/courses/${numCourseId}`} className="text-decoration-none text-muted">
          {classSubjects.course_abbreviation || classSubjects.course_name || `Curso ${numCourseId}`}
        </Link>
        <span className="text-muted">/</span>
        <Link to={`/courses/${numCourseId}/classes/${numClassId}`} className="text-decoration-none text-muted">
          {classSubjects.class_name}
        </Link>
        <span className="text-muted">/</span>
        <span className="fw-medium text-dark">Disciplinas</span>
      </div>

      {/* Alertas de erro */}
      {addSubject.isError && (
        <CAlert color="danger" dismissible onClose={() => addSubject.reset()}>
          <strong>Erro ao adicionar:</strong> {addSubject.error?.response?.data?.detail || 'Erro desconhecido'}
        </CAlert>
      )}
      {updateTeacher.isError && (
        <CAlert color="danger" dismissible onClose={() => updateTeacher.reset()}>
          <strong>Erro ao atribuir professor:</strong> {updateTeacher.error?.response?.data?.detail || 'Erro desconhecido'}
        </CAlert>
      )}
      {removeSubject.isError && (
        <CAlert color="danger" dismissible onClose={() => removeSubject.reset()}>
          <strong>Erro ao remover:</strong> {removeSubject.error?.response?.data?.detail || 'Erro desconhecido'}
        </CAlert>
      )}

      {/* Header da Turma */}
      <CCard className="mb-4 border-0 shadow-sm">
        <CCardBody>
          <div className="d-flex justify-content-between align-items-start">
            <div>
              <div className="d-flex align-items-center gap-2 mb-2">
                <h3 className="mb-0 fw-bold">{classSubjects.class_name}</h3>
                <CBadge color="primary" shape="rounded-pill">
                  {gradeLabels[classSubjects.grade_level] || `${classSubjects.grade_level}.º ano`}
                </CBadge>
              </div>
              {classSubjects.course_name && (
                <div className="d-flex align-items-center gap-1 mb-2 text-muted" style={{ fontSize: '0.9rem' }}>
                  <CIcon icon={cilBookmark} size="sm" />
                  <span>{classSubjects.course_name}</span>
                  {classSubjects.course_abbreviation && (
                    <CBadge color="light" className="text-dark ms-1">{classSubjects.course_abbreviation}</CBadge>
                  )}
                </div>
              )}
              {/* Stats */}
              <div className="d-flex gap-4 mt-1" style={{ fontSize: '0.85rem' }}>
                <div className="d-flex align-items-center gap-1 text-muted">
                  <CIcon icon={cilBook} size="sm" />
                  <span>{stats.total} disciplinas</span>
                </div>
                <div className="d-flex align-items-center gap-1 text-success">
                  <CIcon icon={cilCheckCircle} size="sm" />
                  <span>{stats.assigned} com professor</span>
                </div>
                {stats.pending > 0 && (
                  <div className="d-flex align-items-center gap-1 text-warning">
                    <CIcon icon={cilWarning} size="sm" />
                    <span>{stats.pending} sem professor</span>
                  </div>
                )}
              </div>
            </div>
            <CButton 
              color="primary" 
              onClick={() => setShowAddModal(true)}
              disabled={isUpdating}
            >
              <CIcon icon={cilUserPlus} className="me-1" />
              Adicionar Disciplina
            </CButton>
          </div>
        </CCardBody>
      </CCard>

      {/* Lista de Disciplinas */}
      <CCard className="border-0 shadow-sm">
        <CCardHeader className="bg-transparent d-flex align-items-center gap-2">
          <CIcon icon={cilPeople} className="text-primary" />
          <strong>Disciplinas e Professores</strong>
          <CBadge color="primary" shape="rounded-pill">{stats.total}</CBadge>
        </CCardHeader>
        <CCardBody>
          {classSubjects.subjects.length === 0 ? (
            <div className="text-center py-4">
              <CIcon icon={cilBook} size="3xl" className="text-muted mb-3" />
              <p className="text-muted mb-3">Nenhuma disciplina associada a esta turma.</p>
              <CButton color="primary" onClick={() => setShowAddModal(true)}>
                <CIcon icon={cilUserPlus} className="me-1" />
                Adicionar Primeira Disciplina
              </CButton>
            </div>
          ) : (
            classSubjects.subjects.map(subject => (
              <SubjectRow
                key={subject.id}
                subject={subject}
                classId={numClassId}
                onRemove={handleRemoveSubject}
                onTeacherChange={handleTeacherChange}
                isUpdating={isUpdating}
              />
            ))
          )}
        </CCardBody>
      </CCard>

      {/* Modal: Adicionar Disciplina */}
      <CModal visible={showAddModal} onClose={() => setShowAddModal(false)}>
        <CModalHeader>
          <CModalTitle>Adicionar Disciplina</CModalTitle>
        </CModalHeader>
        <CModalBody>
          {availableLoading ? (
            <div className="text-center py-3">
              <CSpinner size="sm" /> A carregar disciplinas...
            </div>
          ) : availableSubjects?.length === 0 ? (
            <CAlert color="info" className="mb-0">
              Todas as disciplinas já estão associadas a esta turma.
            </CAlert>
          ) : (
            <CFormSelect
              value={selectedSubjectToAdd}
              onChange={(e) => setSelectedSubjectToAdd(e.target.value)}
            >
              <option value="">Selecionar disciplina...</option>
              {(availableSubjects || []).map(subject => (
                <option key={subject.id} value={subject.id}>
                  {subject.name}
                </option>
              ))}
            </CFormSelect>
          )}
        </CModalBody>
        <CModalFooter>
          <CButton color="secondary" onClick={() => setShowAddModal(false)}>
            Cancelar
          </CButton>
          <CButton 
            color="primary" 
            onClick={handleAddSubject}
            disabled={!selectedSubjectToAdd || addSubject.isPending}
          >
            {addSubject.isPending ? <CSpinner size="sm" /> : 'Adicionar'}
          </CButton>
        </CModalFooter>
      </CModal>
    </div>
  )
}

export default ClassSubjects
