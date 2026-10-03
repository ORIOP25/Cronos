import { useState, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { toast } from 'react-hot-toast'
import {
  CCard, CCardBody, CCardHeader, CButton, CAlert,
  CBadge, CSpinner, CFormFeedback, CFormSelect,
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
} from '../features/catalog/data'
import Breadcrumbs from '../components/Breadcrumbs'
import ConfirmationModal from '../components/ConfirmationModal'
import FeedbackBanner from '../components/FeedbackBanner'
import RoomTypeBadge from '../components/RoomTypeBadge'
import { getApiErrorMessage, isApiErrorBlock, isApiErrorTransient } from '../utils/apiErrors'
import { useAttemptScope } from '../hooks/useAttemptScope'
import { formatGradeLevel } from '../utils/presentation'

// ==========================================
//  HELPERS
// ==========================================

// ==========================================
//  SUB-COMPONENT: Card de disciplina com dropdown de professor
// ==========================================
const SubjectRow = ({ 
  subject, 
  onRemove,
  onTeacherChange,
  isUpdating,
  canEditTeacher = true,
  canRemove = true,
  teacherError = '',
}) => {
  const { data: eligibleTeachers, isLoading: teachersLoading } = useEligibleTeachers(subject.subject_id)
  const teacherSelectId = `class-subject-teacher-${subject.subject_id}`
  const teacherErrorId = `class-subject-teacher-error-${subject.subject_id}`
  
  const handleTeacherChange = (e) => {
    const teacherId = e.target.value ? Number.parseInt(e.target.value, 10) : null
    onTeacherChange(subject.subject_id, teacherId)
  }

  return (
    <CCard className="mb-2 border shadow-sm">
      <CCardBody className="py-2 px-3">
        <div className="row align-items-center g-2">
          {/* Info da Disciplina */}
          <div className="col-12 col-md-5">
            <div className="d-flex align-items-center gap-2">
              <CIcon icon={cilBook} className="text-info flex-shrink-0" size="sm" />
              <span className="fw-medium text-break" style={{ minWidth: 0 }}>{subject.subject_name}</span>
              <RoomTypeBadge type={subject.required_room_type} />
            </div>
          </div>

          {/* Dropdown de Professor */}
          <div className="col-12 col-md-5">
            <div className="d-flex align-items-center gap-2">
              {teachersLoading ? (
                <CSpinner size="sm" />
              ) : (
                <CFormSelect
                  id={teacherSelectId}
                  size="sm"
                  className="flex-grow-1"
                  aria-label={`Professor de ${subject.subject_name}`}
                  value={subject.teacher_id || ''}
                  onChange={handleTeacherChange}
                  disabled={isUpdating || !canEditTeacher}
                  invalid={Boolean(teacherError)}
                  aria-invalid={Boolean(teacherError) || undefined}
                  aria-describedby={teacherError ? teacherErrorId : undefined}
                  data-tutorial-target="class-subject-teacher"
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
                <CIcon icon={cilCheckCircle} className="text-success flex-shrink-0" title="Professor atribuído" />
              ) : (
                <CIcon icon={cilWarning} className="text-warning flex-shrink-0" title="Sem professor" />
              )}
            </div>
            {teacherError && (
              <CFormFeedback id={teacherErrorId} invalid className="d-block" role="alert">{teacherError}</CFormFeedback>
            )}
          </div>

          {/* Botão Remover */}
          {canRemove && <div className="col-auto col-md-2 ms-auto text-end">
            <CButton
              color="danger"
              variant="ghost"
              size="sm"
              aria-label={`Remover ${subject.subject_name}`}
              onClick={() => onRemove(subject.subject_id)}
              disabled={isUpdating || !canRemove}
              title="Remover disciplina"
            >
              <CIcon icon={cilTrash} />
            </CButton>
          </div>}
        </div>
      </CCardBody>
    </CCard>
  )
}

// ==========================================
//  COMPONENT PRINCIPAL: ClassSubjects
// ==========================================
const ClassSubjects = ({ courseIdOverride, classIdOverride, navigationDisabled = false, readOnly = false, allowedActions }) => {
  const params = useParams()
  const courseId = courseIdOverride ?? params.courseId
  const classId = classIdOverride ?? params.classId
  const navigate = useNavigate()
  const numClassId = Number(classId)
  const numCourseId = Number(courseId)
  const isTutorial = Array.isArray(allowedActions)
  const canEditTeacher = !readOnly && (!isTutorial || allowedActions.includes('UPDATE_CLASS_SUBJECT_TEACHER'))
  const canAdd = !readOnly && !isTutorial
  const canRemove = !readOnly && !isTutorial

  // State para modal de adicionar disciplina
  const [showAddModal, setShowAddModal] = useState(false)
  const [selectedSubjectToAdd, setSelectedSubjectToAdd] = useState('')
  const [subjectToRemove, setSubjectToRemove] = useState(null)
  const [blockedMessage, setBlockedMessage] = useState('')
  const [teacherBlock, setTeacherBlock] = useState(null)

  // Data hooks
  const { data: classSubjects, isLoading, error } = useClassSubjects(numClassId)
  const { data: availableSubjects, isLoading: availableLoading } = useAvailableSubjects(numClassId)

  // Mutation hooks
  const addSubject = useAddClassSubject()
  const updateTeacher = useUpdateClassSubjectTeacher()
  const removeSubject = useRemoveClassSubject()
  const attemptScope = useAttemptScope()

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
      { classId: numClassId, subjectId: Number.parseInt(selectedSubjectToAdd, 10) },
      attemptScope.guard({
        onSuccess: () => {
          setShowAddModal(false)
          setSelectedSubjectToAdd('')
          toast.success('Disciplina adicionada.')
        },
        onError: (error) => toast.error(getApiErrorMessage(error, 'Não foi possível adicionar a disciplina. Tente novamente.')),
      })
    )
  }

  const handleRemoveSubject = (subjectId) => {
    const subject = classSubjects?.subjects?.find(item => item.subject_id === subjectId)
    setSubjectToRemove(subject || { subject_id: subjectId, subject_name: 'esta disciplina' })
  }

  const confirmRemoveSubject = () => {
    if (!subjectToRemove) return
    removeSubject.mutate(
      { classId: numClassId, subjectId: subjectToRemove.subject_id },
      attemptScope.guard({
        onSuccess: () => {
          setSubjectToRemove(null)
          setBlockedMessage('')
          toast.success('Disciplina removida.')
        },
        onError: (error) => {
          setSubjectToRemove(null)
          if (isApiErrorBlock(error)) setBlockedMessage(getApiErrorMessage(error))
          else toast.error(getApiErrorMessage(error, 'Não foi possível remover a disciplina. Tente novamente.'))
        },
      })
    )
  }

  const handleTeacherChange = (subjectId, teacherId) => {
    if (!canEditTeacher) return
    updateTeacher.mutate(
      { classId: numClassId, subjectId, teacherId },
      attemptScope.guard({
        onSuccess: () => {
          setTeacherBlock(null)
          toast.success('Professor atualizado.')
        },
        onError: (error) => {
          const message = getApiErrorMessage(error, 'Não foi possível atribuir o professor. Tente novamente.')
          if (isApiErrorTransient(error)) toast.error(message)
          else setTeacherBlock({ subjectId, message })
        },
      })
    )
  }

  const renderAddModalBody = () => {
    if (availableLoading) {
      return (
        <div className="text-center py-3">
          <CSpinner size="sm" /> A carregar disciplinas...
        </div>
      )
    }
    if (availableSubjects?.length === 0) {
      return (
        <CAlert color="info" className="mb-0">
          Todas as disciplinas já estão associadas a esta turma.
        </CAlert>
      )
    }
    return (
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
    )
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
          <strong>Erro:</strong> {getApiErrorMessage(error, 'Turma não encontrada.')}
        </CAlert>
        <CButton color="light" onClick={() => { if (!navigationDisabled) navigate(`/courses/${numCourseId}`) }} disabled={navigationDisabled}>
          <CIcon icon={cilArrowLeft} className="me-1" /> Voltar ao Curso
        </CButton>
      </div>
    )
  }

  return (
    <div className="p-4">
      <Breadcrumbs items={[
        { label: 'Cursos', to: '/courses' },
        { label: classSubjects.course_abbreviation || classSubjects.course_name || `Curso ${numCourseId}`, to: `/courses/${numCourseId}` },
        { label: classSubjects.class_name, to: `/courses/${numCourseId}/classes/${numClassId}` },
        { label: 'Disciplinas' },
      ]} />

      {blockedMessage && (
        <div className="mb-3"><FeedbackBanner tone="danger">{blockedMessage}</FeedbackBanner></div>
      )}

      {/* Header da Turma */}
      <CCard className="mb-4 border-0 shadow-sm">
        <CCardBody>
          <div className="d-flex justify-content-between align-items-start">
            <div>
              <div className="d-flex align-items-center gap-2 mb-2">
                <h3 className="mb-0 fw-bold">{classSubjects.class_name}</h3>
                <CBadge color="primary" shape="rounded-pill">
                  {formatGradeLevel(classSubjects.grade_level)}
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
              disabled={isUpdating || !canAdd}
              data-tutorial-target="add-class-subject"
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
        </CCardHeader>
        <CCardBody>
          {classSubjects.subjects.length === 0 ? (
            <div className="text-center py-4">
              <CIcon icon={cilBook} size="3xl" className="text-muted mb-3" />
              <p className="text-muted mb-3">Nenhuma disciplina associada a esta turma.</p>
              <CButton color="primary" onClick={() => setShowAddModal(true)} disabled={!canAdd} data-tutorial-target="add-class-subject">
                <CIcon icon={cilUserPlus} className="me-1" />
                Adicionar Primeira Disciplina
              </CButton>
            </div>
          ) : (
            classSubjects.subjects.map(subject => (
              <SubjectRow
                key={subject.id}
                subject={subject}
                onRemove={handleRemoveSubject}
                onTeacherChange={handleTeacherChange}
                isUpdating={isUpdating}
                canEditTeacher={canEditTeacher}
                canRemove={canRemove}
                teacherError={teacherBlock?.subjectId === subject.subject_id ? teacherBlock.message : ''}
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
          {renderAddModalBody()}
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
      <ConfirmationModal
        visible={Boolean(subjectToRemove)}
        onClose={() => setSubjectToRemove(null)}
        onConfirm={confirmRemoveSubject}
        title="Confirmar remoção da disciplina"
        message={`Remover ${subjectToRemove?.subject_name || 'esta disciplina'} desta turma?`}
        confirmText="Remover"
        isLoading={removeSubject.isPending}
        variant="danger"
      />
    </div>
  )
}

export default ClassSubjects
