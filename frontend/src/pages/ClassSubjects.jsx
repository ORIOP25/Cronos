import { useState, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { toast } from 'react-hot-toast'
import {
  CCard, CCardBody, CCardHeader, CButton,
  CBadge, CSpinner, CFormCheck, CFormFeedback, CFormSelect,
  CModal, CModalHeader, CModalTitle,
  CModalBody, CModalFooter,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import {
  cilArrowLeft, cilBook, cilUserPlus, cilTrash, cilPeople,
  cilBookmark, cilCheckCircle, cilWarning, cilLink,
} from '@coreui/icons'
import {
  useClassSubjects,
  useAvailableSubjects,
  useEligibleTeachers,
  useAddClassSubject,
  useUpdateClassSubject,
  useRemoveClassSubject,
  useJointCandidates,
  useCreateJointGroup,
  useUpdateJointGroup,
  useDeleteJointGroup,
} from '../features/catalog/data'
import Breadcrumbs from '../components/Breadcrumbs'
import ConfirmationModal from '../components/ConfirmationModal'
import FeedbackBanner from '../components/FeedbackBanner'
import RoomTypeBadge from '../components/RoomTypeBadge'
import { getApiErrorMessage, getApiErrorCode, isApiErrorBlock, isApiErrorTransient } from '../utils/apiErrors'
import { useAttemptScope } from '../hooks/useAttemptScope'
import { formatGradeLevel } from '../utils/presentation'

// ==========================================
//  HELPERS
// ==========================================

const formatModuleLabel = (module) => {
  const code = module.code ? `${module.code} ` : ''
  return `${code}${module.name} · ${module.hours_total} h`
}

const jointOtherClassNames = (subject, classId) => (
  (subject?.joint_group?.classes ?? [])
    .filter((cls) => cls.class_id !== classId)
    .map((cls) => cls.class_name)
    .join(', ')
)

// ==========================================
//  SUB-COMPONENT: Card de disciplina com dropdown de professor
// ==========================================
const SubjectRow = ({ 
  subject, 
  classId,
  onRemove,
  onTeacherChange,
  onModulesChange,
  onOpenJoint,
  onUndoJoint,
  isUpdating,
  canEditTeacher = true,
  canEditModules = true,
  canEditJoint = true,
  canRemove = true,
  teacherError = '',
  moduleError = '',
}) => {
  const { data: eligibleTeachers, isLoading: teachersLoading } = useEligibleTeachers(subject.subject_id)
  const [modulesOpen, setModulesOpen] = useState(false)
  const teacherSelectId = `class-subject-teacher-${subject.subject_id}`
  const teacherErrorId = `class-subject-teacher-error-${subject.subject_id}`
  const modulesListId = `class-subject-modules-${subject.subject_id}`
  const moduleErrorId = `class-subject-modules-error-${subject.subject_id}`

  const modules = subject.modules || []
  const selectedModules = modules.filter((module) => module.selected)
  const selectedHours = selectedModules.reduce((total, module) => total + module.hours_total, 0)

  const jointGroup = subject.joint_group
  const jointModuleIds = new Set(jointGroup?.module_ids ?? [])
  const jointOtherNames = (jointGroup?.classes ?? [])
    .filter((cls) => cls.class_id !== classId)
    .map((cls) => cls.class_name)
    .join(', ')
  const jointModuleLabels = (jointGroup?.module_ids ?? [])
    .map((id) => {
      const module = modules.find((item) => item.id === id)
      return module ? (module.code || module.name) : null
    })
    .filter(Boolean)
    .join(', ')
  
  const handleTeacherChange = (e) => {
    const teacherId = e.target.value ? Number.parseInt(e.target.value, 10) : null
    onTeacherChange(subject.subject_id, teacherId)
  }

  const handleModuleToggle = (moduleId) => {
    const nextModuleIds = modules
      .filter((module) => (module.id === moduleId ? !module.selected : module.selected))
      .map((module) => module.id)
    onModulesChange(subject.subject_id, nextModuleIds)
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

        {/* Checklist de módulos */}
        <div className="mt-2 d-flex flex-wrap align-items-center gap-2">
          <CButton
            color="secondary"
            variant="outline"
            size="sm"
            id={`class-subject-modules-summary-${subject.subject_id}`}
            aria-expanded={modulesOpen}
            aria-controls={modulesListId}
            onClick={() => setModulesOpen((open) => !open)}
            data-tutorial-target="class-subject-modules"
          >
            Módulos: {selectedModules.length} de {modules.length} · {selectedHours} h
          </CButton>
          {selectedModules.length === 0 && (
            <span className="text-warning d-inline-flex align-items-center gap-1" style={{ fontSize: '0.85rem' }}>
              <CIcon icon={cilWarning} size="sm" /> Sem módulos
            </span>
          )}
        </div>

        <div id={modulesListId} hidden={!modulesOpen} className="mt-2">
          {modules.length === 0 ? (
            <p className="text-muted mb-0" style={{ fontSize: '0.85rem' }}>
              Esta disciplina não tem módulos. Adicione-os em Disciplinas.
            </p>
          ) : (
            modules.map((module) => {
              const isJoint = jointModuleIds.has(module.id)
              return (
                <div key={module.id}>
                  <CFormCheck
                    id={`class-subject-module-${subject.subject_id}-${module.id}`}
                    label={formatModuleLabel(module)}
                    checked={Boolean(module.selected)}
                    disabled={isUpdating || !canEditModules || isJoint}
                    onChange={() => handleModuleToggle(module.id)}
                  />
                  {isJoint && (
                    <div className="text-muted ms-4" style={{ fontSize: '0.8rem' }}>
                      <CIcon icon={cilLink} size="sm" className="me-1" />
                      Retire primeiro este módulo da aula conjunta.
                    </div>
                  )}
                </div>
              )
            })
          )}
        </div>
        {moduleError && (
          <CFormFeedback id={moduleErrorId} invalid className="d-block" role="alert">{moduleError}</CFormFeedback>
        )}

        {/* Aula conjunta */}
        <div className="mt-2">
          {jointGroup ? (
            <div className="d-flex flex-wrap align-items-center gap-2">
              <span className="text-muted" style={{ fontSize: '0.85rem' }}>
                Em conjunto com {jointOtherNames} · Módulos {jointModuleLabels}
              </span>
              {canEditJoint && (
                <>
                  <CButton color="secondary" variant="outline" size="sm" onClick={() => onOpenJoint(subject)}>
                    Editar
                  </CButton>
                  <CButton color="danger" variant="outline" size="sm" onClick={() => onUndoJoint(subject)}>
                    Desfazer
                  </CButton>
                </>
              )}
            </div>
          ) : (
            canEditJoint && (
              <CButton
                color="secondary"
                variant="outline"
                size="sm"
                onClick={() => onOpenJoint(subject)}
                data-tutorial-target="joint-group-create"
              >
                Dar em conjunto com…
              </CButton>
            )
          )}
        </div>
      </CCardBody>
    </CCard>
  )
}

// ==========================================
//  MODAL: Aula conjunta
// ==========================================
const JOINT_ERROR_FIELDS = {
  JOINT_TOO_FEW_CLASSES: 'classes',
  JOINT_CLASS_WITHOUT_SUBJECT: 'classes',
  JOINT_CLASS_ALREADY_JOINED: 'classes',
  JOINT_CLASS_STARTED: 'classes',
  JOINT_NO_MODULES: 'modules',
  JOINT_MODULE_NOT_SELECTED: 'modules',
  JOINT_MODULE_STARTED: 'modules',
  JOINT_TEACHER_NOT_ELIGIBLE: 'teacher',
  teacher_competency_missing: 'teacher',
}

const formatClassCandidate = (candidate) => (
  `${candidate.class_name} · ${candidate.course_abbreviation} · ${formatGradeLevel(candidate.grade_level)}`
)

const jointCommonModuleIds = (sourceSelectedIds, rows, fallbackIds, modules) => {
  let ids = sourceSelectedIds
  for (const row of rows) {
    const rowSelected = Array.isArray(row.selected_module_ids) ? row.selected_module_ids : fallbackIds
    ids = ids.filter((id) => rowSelected.includes(id))
  }
  return ids.filter((id) => modules.some((module) => module.id === id))
}

const jointStartedModuleIds = (sourceStartedIds, rows) => {
  const started = new Set(sourceStartedIds)
  for (const row of rows) {
    for (const id of row.started_module_ids ?? []) started.add(id)
  }
  return started
}

const JointGroupModal = ({
  subject,
  classId,
  jointGroup,
  onClose,
  onSubmit,
  isPending,
  error,
}) => {
  const { data: candidates = [], isLoading: candidatesLoading } = useJointCandidates(
    subject.subject_id,
    classId,
    jointGroup?.id,
    true,
  )
  const { data: eligibleTeachers = [] } = useEligibleTeachers(subject.subject_id)

  const modules = useMemo(() => subject.modules || [], [subject.modules])
  const sourceSelectedIds = useMemo(
    () => modules.filter((module) => module.selected).map((module) => module.id),
    [modules],
  )
  const sourceCandidate = candidates.find((candidate) => candidate.class_id === classId) ?? null
  const sourceStartedIds = useMemo(
    () => sourceCandidate?.started_module_ids ?? [],
    [sourceCandidate],
  )

  // Every class shown: the other members of the edited group plus any addable candidate.
  const classRows = useMemo(() => {
    const byId = new Map()
    if (jointGroup) {
      for (const cls of jointGroup.classes ?? []) {
        if (cls.class_id === classId) continue
        byId.set(cls.class_id, {
          class_id: cls.class_id,
          class_name: cls.class_name,
          course_abbreviation: cls.course_abbreviation,
          grade_level: cls.grade_level,
          selected_module_ids: null,
          started_module_ids: [],
          teacher_id: null,
        })
      }
    }
    for (const candidate of candidates) {
      if (candidate.class_id === classId) continue
      const existing = byId.get(candidate.class_id)
      byId.set(candidate.class_id, {
        class_id: candidate.class_id,
        class_name: candidate.class_name ?? existing?.class_name,
        course_abbreviation: candidate.course_abbreviation ?? existing?.course_abbreviation,
        grade_level: candidate.grade_level ?? existing?.grade_level,
        selected_module_ids: candidate.selected_module_ids ?? existing?.selected_module_ids ?? null,
        started_module_ids: candidate.started_module_ids ?? [],
        teacher_id: candidate.teacher_id ?? null,
      })
    }
    return [...byId.values()]
  }, [jointGroup, candidates, classId])

  const [chosenClassIds, setChosenClassIds] = useState(() => (
    jointGroup
      ? (jointGroup.classes ?? []).filter((cls) => cls.class_id !== classId).map((cls) => cls.class_id)
      : []
  ))
  const [checkedModuleIds, setCheckedModuleIds] = useState(() => jointGroup?.module_ids ?? [])
  const [teacherId, setTeacherId] = useState(() => (
    jointGroup?.teacher_id != null ? String(jointGroup.teacher_id) : ''
  ))

  const chosenRows = classRows.filter((row) => chosenClassIds.includes(row.class_id))
  const fallbackIds = useMemo(() => jointGroup?.module_ids ?? [], [jointGroup])

  const startedModuleIds = useMemo(
    () => jointStartedModuleIds(sourceStartedIds, chosenRows),
    [sourceStartedIds, chosenRows],
  )
  const commonModuleIds = useMemo(
    () => jointCommonModuleIds(sourceSelectedIds, chosenRows, fallbackIds, modules),
    [sourceSelectedIds, chosenRows, fallbackIds, modules],
  )

  // J19: no class may be added or removed once any previous joint module began.
  const classLocked = useMemo(
    () => fallbackIds.some((id) => startedModuleIds.has(id)),
    [fallbackIds, startedModuleIds],
  )

  const sourceTeacherId = sourceCandidate?.teacher_id ?? subject.teacher_id ?? null
  const memberTeacherIds = []
  if (sourceTeacherId != null) memberTeacherIds.push(sourceTeacherId)
  for (const row of chosenRows) {
    if (row.teacher_id != null) memberTeacherIds.push(row.teacher_id)
  }
  const distinctTeacherIds = [...new Set(memberTeacherIds)]
  const requiresTeacherChoice = distinctTeacherIds.length !== 1
  const effectiveTeacherId = requiresTeacherChoice ? teacherId : String(distinctTeacherIds[0])

  const errorField = error ? JOINT_ERROR_FIELDS[error.code] ?? null : null
  const genericError = error && !errorField ? error.message : ''

  const chosenNames = chosenRows.map((row) => row.class_name).join(', ')

  const handleClassToggle = (row) => {
    if (classLocked || isPending) return
    const nextIds = chosenClassIds.includes(row.class_id)
      ? chosenClassIds.filter((id) => id !== row.class_id)
      : [...chosenClassIds, row.class_id]
    setChosenClassIds(nextIds)
    const nextRows = classRows.filter((item) => nextIds.includes(item.class_id))
    const nextCommon = jointCommonModuleIds(sourceSelectedIds, nextRows, fallbackIds, modules)
    if (jointGroup) {
      setCheckedModuleIds((previous) => previous.filter((id) => nextCommon.includes(id)))
    } else {
      const started = jointStartedModuleIds(sourceStartedIds, nextRows)
      setCheckedModuleIds(nextCommon.filter((id) => !started.has(id)))
      const nextTeachers = [...new Set(
        [sourceTeacherId, ...nextRows.map((item) => item.teacher_id)].filter((value) => value != null),
      )]
      if (nextTeachers.length !== 1) setTeacherId('')
    }
  }

  const handleModuleToggle = (moduleId) => {
    setCheckedModuleIds((previous) => (
      previous.includes(moduleId)
        ? previous.filter((id) => id !== moduleId)
        : [...previous, moduleId]
    ))
  }

  const submittedModuleIds = checkedModuleIds.filter((id) => commonModuleIds.includes(id))
  const canSubmit = chosenClassIds.length >= 1
    && submittedModuleIds.length >= 1
    && Boolean(effectiveTeacherId)

  const handleSubmit = () => {
    if (!canSubmit) return
    onSubmit({
      classIds: [classId, ...chosenClassIds],
      moduleIds: submittedModuleIds,
      teacherId: Number(effectiveTeacherId),
    })
  }

  return (
    <CModal visible onClose={onClose} size="lg" alignment="center">
      <CModalHeader>
        <CModalTitle>{`Aula conjunta · ${subject.subject_name}`}</CModalTitle>
      </CModalHeader>
      <CModalBody>
        {genericError && (
          <div className="mb-3"><FeedbackBanner tone="danger">{genericError}</FeedbackBanner></div>
        )}

        <fieldset className="mb-3">
          <legend className="h6">Turmas</legend>
          {candidatesLoading ? (
            <CSpinner size="sm" />
          ) : classRows.length === 0 ? (
            <p className="text-muted small mb-0">Não há turmas candidatas para esta junção.</p>
          ) : (
            classRows.map((row) => (
              <CFormCheck
                key={row.class_id}
                id={`joint-class-${row.class_id}`}
                label={formatClassCandidate(row)}
                checked={chosenClassIds.includes(row.class_id)}
                disabled={isPending || classLocked}
                onChange={() => handleClassToggle(row)}
              />
            ))
          )}
          {classLocked && (
            <p className="text-muted small mb-0 mt-1">
              A aula conjunta já começou. Não pode juntar nem retirar turmas.
            </p>
          )}
          {errorField === 'classes' && (
            <div className="text-danger small mt-1" role="alert">{error.message}</div>
          )}
        </fieldset>

        <fieldset className="mb-3">
          <legend className="h6">Módulos conjuntos</legend>
          {modules.length === 0 ? (
            <p className="text-muted small mb-0">Esta disciplina não tem módulos.</p>
          ) : (
            modules.map((module) => {
              const isStarted = startedModuleIds.has(module.id)
              const isCommon = commonModuleIds.includes(module.id)
              return (
                <div key={module.id}>
                  <CFormCheck
                    id={`joint-module-${module.id}`}
                    label={formatModuleLabel(module)}
                    checked={isCommon && checkedModuleIds.includes(module.id)}
                    disabled={!isCommon || isStarted || isPending}
                    onChange={() => handleModuleToggle(module.id)}
                  />
                  {isStarted && (
                    <div className="text-muted ms-4" style={{ fontSize: '0.8rem' }}>Já começou</div>
                  )}
                </div>
              )
            })
          )}
          {errorField === 'modules' && (
            <div className="text-danger small mt-1" role="alert">{error.message}</div>
          )}
        </fieldset>

        {requiresTeacherChoice && (
          <div className="mb-3">
            <CFormSelect
              id="jointTeacher"
              label="Professor da aula conjunta"
              value={teacherId}
              onChange={(event) => setTeacherId(event.target.value)}
              disabled={isPending}
            >
              <option value="">— Selecionar professor —</option>
              {eligibleTeachers.map((teacher) => (
                <option key={teacher.id} value={teacher.id}>{teacher.name}</option>
              ))}
            </CFormSelect>
            {errorField === 'teacher' && (
              <div className="text-danger small mt-1" role="alert">{error.message}</div>
            )}
          </div>
        )}

        {chosenRows.length > 0 && (
          <p className="text-muted small mb-0">Esta alteração também muda {chosenNames}.</p>
        )}
      </CModalBody>
      <CModalFooter>
        <CButton color="secondary" variant="outline" onClick={onClose} disabled={isPending}>
          Cancelar
        </CButton>
        <CButton color="primary" onClick={handleSubmit} disabled={!canSubmit || isPending}>
          {jointGroup ? 'Guardar junção' : 'Criar junção'}
        </CButton>
      </CModalFooter>
    </CModal>
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
  const canEditModules = !readOnly && !isTutorial
  const canEditJoint = !readOnly && !isTutorial
  const canAdd = !readOnly && !isTutorial
  const canRemove = !readOnly && !isTutorial

  // State para modal de adicionar disciplina
  const [showAddModal, setShowAddModal] = useState(false)
  const [selectedSubjectToAdd, setSelectedSubjectToAdd] = useState('')
  const [subjectToRemove, setSubjectToRemove] = useState(null)
  const [blockedMessage, setBlockedMessage] = useState('')
  const [teacherBlock, setTeacherBlock] = useState(null)
  const [moduleBlock, setModuleBlock] = useState(null)
  const [jointSubject, setJointSubject] = useState(null)
  const [jointToUndo, setJointToUndo] = useState(null)
  const [jointError, setJointError] = useState(null)
  const [teacherConfirm, setTeacherConfirm] = useState(null)

  // Data hooks
  const { data: classSubjects, isLoading, error } = useClassSubjects(numClassId)
  const { data: availableSubjects, isLoading: availableLoading } = useAvailableSubjects(numClassId)

  // Mutation hooks
  const addSubject = useAddClassSubject()
  const updateClassSubject = useUpdateClassSubject()
  const removeSubject = useRemoveClassSubject()
  const createJointGroup = useCreateJointGroup()
  const updateJointGroup = useUpdateJointGroup()
  const deleteJointGroup = useDeleteJointGroup()
  const attemptScope = useAttemptScope()

  const isUpdating = addSubject.isPending
    || updateClassSubject.isPending
    || removeSubject.isPending
    || createJointGroup.isPending
    || updateJointGroup.isPending
    || deleteJointGroup.isPending

  // Stats
  const stats = useMemo(() => {
    if (!classSubjects?.subjects) return { total: 0, assigned: 0, pending: 0, withoutModules: 0 }
    const total = classSubjects.subjects.length
    const assigned = classSubjects.subjects.filter(s => s.teacher_id).length
    const withoutModules = classSubjects.subjects.filter(
      s => !(s.modules || []).some(module => module.selected),
    ).length
    return { total, assigned, pending: total - assigned, withoutModules }
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

  const performTeacherChange = (subjectId, teacherId) => {
    updateClassSubject.mutate(
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

  const handleTeacherChange = (subjectId, teacherId) => {
    if (!canEditTeacher) return
    const subject = classSubjects?.subjects?.find(item => item.subject_id === subjectId)
    const otherNames = jointOtherClassNames(subject, numClassId)
    if (otherNames && teacherId !== subject.teacher_id) {
      setTeacherConfirm({ subjectId, teacherId, otherNames })
      return
    }
    performTeacherChange(subjectId, teacherId)
  }

  const confirmTeacherChange = () => {
    if (!teacherConfirm) return
    const { subjectId, teacherId } = teacherConfirm
    setTeacherConfirm(null)
    performTeacherChange(subjectId, teacherId)
  }

  const handleModulesChange = (subjectId, moduleIds) => {
    if (!canEditModules) return
    updateClassSubject.mutate(
      { classId: numClassId, subjectId, moduleIds },
      attemptScope.guard({
        onSuccess: () => {
          setModuleBlock(null)
          toast.success('Módulos atualizados.', { id: 'class-subject-modules' })
        },
        onError: (error) => {
          const message = getApiErrorMessage(error, 'Não foi possível atualizar os módulos. Tente novamente.')
          if (isApiErrorTransient(error)) toast.error(message)
          else setModuleBlock({ subjectId, message })
        },
      })
    )
  }

  const openJoint = (subject) => {
    setJointError(null)
    setJointSubject(subject)
  }

  const closeJoint = () => {
    setJointSubject(null)
    setJointError(null)
  }

  const handleJointSubmit = ({ classIds, moduleIds, teacherId }) => {
    if (!jointSubject) return
    const existing = jointSubject.joint_group
    const onSuccess = () => {
      closeJoint()
      toast.success(existing ? 'Aula conjunta atualizada.' : 'Aula conjunta criada.')
    }
    const onError = (error) => {
      const message = getApiErrorMessage(error, 'Não foi possível guardar a aula conjunta. Tente novamente.')
      if (isApiErrorTransient(error)) toast.error(message)
      else setJointError({ code: getApiErrorCode(error), message })
    }
    if (existing) {
      updateJointGroup.mutate({
        groupId: existing.id,
        classIds,
        moduleIds,
        teacherId,
        previousClassIds: existing.classes.map((cls) => cls.class_id),
      }, attemptScope.guard({ onSuccess, onError }))
    } else {
      createJointGroup.mutate({
        subjectId: jointSubject.subject_id,
        classIds,
        moduleIds,
        teacherId,
      }, attemptScope.guard({ onSuccess, onError }))
    }
  }

  const requestUndoJoint = (subject) => setJointToUndo(subject)

  const confirmUndoJoint = () => {
    if (!jointToUndo?.joint_group) return
    deleteJointGroup.mutate({
      groupId: jointToUndo.joint_group.id,
      classIds: jointToUndo.joint_group.classes.map((cls) => cls.class_id),
    }, attemptScope.guard({
      onSuccess: () => {
        setJointToUndo(null)
        toast.success('Aula conjunta desfeita.')
      },
      onError: (error) => {
        setJointToUndo(null)
        toast.error(getApiErrorMessage(error, 'Não foi possível desfazer a aula conjunta. Tente novamente.'))
      },
    }))
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
        <FeedbackBanner tone="info">
          Todas as disciplinas já estão associadas a esta turma.
        </FeedbackBanner>
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
        <div className="mb-3"><FeedbackBanner tone="danger">
          <strong>Erro:</strong> {getApiErrorMessage(error, 'Turma não encontrada.')}
        </FeedbackBanner></div>
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
                {stats.withoutModules > 0 && (
                  <div className="d-flex align-items-center gap-1 text-warning">
                    <CIcon icon={cilWarning} size="sm" />
                    <span>{stats.withoutModules} sem módulos</span>
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
                classId={numClassId}
                onRemove={handleRemoveSubject}
                onTeacherChange={handleTeacherChange}
                onModulesChange={handleModulesChange}
                onOpenJoint={openJoint}
                onUndoJoint={requestUndoJoint}
                isUpdating={isUpdating}
                canEditTeacher={canEditTeacher}
                canEditModules={canEditModules}
                canEditJoint={canEditJoint}
                canRemove={canRemove}
                teacherError={teacherBlock?.subjectId === subject.subject_id ? teacherBlock.message : ''}
                moduleError={moduleBlock?.subjectId === subject.subject_id ? moduleBlock.message : ''}
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
      {jointSubject && (
        <JointGroupModal
          subject={jointSubject}
          classId={numClassId}
          jointGroup={jointSubject.joint_group}
          onClose={closeJoint}
          onSubmit={handleJointSubmit}
          isPending={createJointGroup.isPending || updateJointGroup.isPending}
          error={jointError}
        />
      )}
      <ConfirmationModal
        visible={Boolean(jointToUndo)}
        onClose={() => setJointToUndo(null)}
        onConfirm={confirmUndoJoint}
        title="Desfazer aula conjunta"
        message={`As turmas ${jointOtherClassNames(jointToUndo, numClassId)} passam a ter ${jointToUndo?.subject_name ?? 'a disciplina'} em separado. É preciso gerar o horário de novo.`}
        confirmText="Desfazer"
        isLoading={deleteJointGroup.isPending}
        variant="warning"
      />
      <ConfirmationModal
        visible={Boolean(teacherConfirm)}
        onClose={() => setTeacherConfirm(null)}
        onConfirm={confirmTeacherChange}
        title="Mudar professor da aula conjunta"
        message={`O professor muda também em ${teacherConfirm?.otherNames ?? ''} (aula conjunta).`}
        confirmText="Mudar professor"
        isLoading={updateClassSubject.isPending}
        variant="warning"
      />
    </div>
  )
}

export default ClassSubjects
