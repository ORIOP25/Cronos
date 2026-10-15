import { useState, useMemo, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { toast } from 'react-hot-toast'
import {
  CCard, CCardBody, CCardHeader, CCol, CRow, CButton,
  CBadge, CSpinner, CFormInput, CProgress, CProgressBar,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import {
  cilArrowLeft, cilPencil, cilSave, cilX,
  cilPeople, cilBook, cilCheckCircle,
  cilBookmark, cilChevronRight, cilSettings,
} from '@coreui/icons'

import {
  useClassDetails,
  useUpdateCourseClass,
  useUpdateClassProgress,
  useClassSubjects,
} from '../features/catalog/data'
import Breadcrumbs from '../components/Breadcrumbs'
import FeedbackBanner from '../components/FeedbackBanner'
import RoomTypeBadge from '../components/RoomTypeBadge'
import { getApiErrorMessage } from '../utils/apiErrors'
import { useAttemptScope } from '../hooks/useAttemptScope'
import { formatGradeLevel } from '../utils/presentation'

// ==========================================
//  HELPERS
// ==========================================

/** Cor da barra de progresso conforme percentagem (exception: red→green gradient) */
const getProgressColor = (pct) => {
  if (pct >= 100) return 'var(--rs-progress-green)'
  if (pct >= 60)  return 'var(--rs-progress-yellow)'
  if (pct >= 30)  return 'var(--rs-progress-orange)'
  return 'var(--rs-progress-red)'
}

// ==========================================
//  SUB-COMPONENT: Linha de módulo com progresso editável
// ==========================================
const ModuleRow = ({ module, isEditing, editValue, onChangeHours }) => {
  // Quando editValue é 0, mostramos string vazia para UX limpa
  const rawEditValue = editValue === 0 ? '' : editValue
  const numericValue = editValue || 0
  const activeHours = isEditing ? numericValue : module.hours_completed
  const pct = module.hours_total > 0
    ? Math.round((activeHours / module.hours_total) * 100)
    : 0
  const displayPct = Math.min(pct, 100)
  const displayHours = activeHours

  const handleInputChange = (e) => {
    const raw = e.target.value
    // Permitir campo vazio (interpretado como 0)
    if (raw === '') {
      onChangeHours(module.id, 0)
      return
    }
    const parsed = Number.parseInt(raw, 10)
    if (!Number.isNaN(parsed)) {
      onChangeHours(module.id, parsed)
    }
  }

  return (
    <div className="py-2 border-bottom">
      <div className="d-flex justify-content-between align-items-center mb-1">
        <div className="d-flex align-items-center gap-2" style={{ minWidth: 0, flex: 1 }}>
          {module.is_completed && !isEditing && (
            <CIcon icon={cilCheckCircle} className="text-success flex-shrink-0" size="sm" />
          )}
          <span className="text-truncate fw-medium" style={{ fontSize: '0.9rem' }}>
            {module.code && <span className="text-muted me-1">{module.code}</span>}
            {module.name}
          </span>
        </div>
        <div className="d-flex align-items-center gap-2 flex-shrink-0 ms-2">
          {isEditing ? (
            <div className="d-flex align-items-center gap-1">
              <CFormInput
                type="number"
                min={0}
                max={module.hours_total}
                value={rawEditValue}
                placeholder="0"
                onChange={handleInputChange}
                size="sm"
                style={{ width: '70px', textAlign: 'center' }}
              />
              <span className="text-muted fw-medium" style={{ fontSize: '0.85rem', whiteSpace: 'nowrap' }}>
                / {module.hours_total}h
              </span>
            </div>
          ) : (
            <span className="text-muted" style={{ fontSize: '0.85rem', whiteSpace: 'nowrap' }}>
              {displayHours}/{module.hours_total}h
            </span>
          )}
          <CBadge
            shape="rounded-pill"
            className="zen-badge-progress"
            style={{ backgroundColor: getProgressColor(displayPct) }}
          >
            {displayPct}%
          </CBadge>
        </div>
      </div>
      <CProgress thin className="mt-1">
        <CProgressBar value={displayPct} style={{ width: `${displayPct}%`, backgroundColor: getProgressColor(displayPct) }} />
      </CProgress>
    </div>
  )
}

// ==========================================
//  SUB-COMPONENT: Card de disciplina com accordion
// ==========================================
const SubjectCard = ({ subject, isEditing, editMap, onChangeHours }) => {
  const pct = Math.round(subject.overall_percentage)

  return (
    <CCard className="border shadow-sm mb-3">
      <CCardHeader className="bg-transparent py-2">
        <div className="d-flex justify-content-between align-items-center">
          <div className="d-flex align-items-center gap-2">
            <CIcon icon={cilBook} className="text-info" size="sm" />
            <strong style={{ fontSize: '0.95rem' }}>{subject.name}</strong>
            <RoomTypeBadge type={subject.required_room_type} />
          </div>
          <div className="d-flex align-items-center gap-2">
            <span className="text-muted" style={{ fontSize: '0.85rem' }}>
              {subject.completed_hours}/{subject.total_hours}h
            </span>
            <CBadge
              shape="rounded-pill"
              className="zen-badge-progress"
              style={{ backgroundColor: getProgressColor(pct) }}
            >
              {pct}%
            </CBadge>
          </div>
        </div>
        <CProgress thin className="mt-2">
          <CProgressBar value={Math.min(pct, 100)} style={{ width: `${Math.min(pct, 100)}%`, backgroundColor: getProgressColor(pct) }} />
        </CProgress>
      </CCardHeader>
      <CCardBody className="py-1 px-3">
        {[...subject.modules]
          .sort((a, b) => a.order - b.order)
          .map(mod => (
            <ModuleRow
              key={mod.id}
              module={mod}
              isEditing={isEditing}
              editValue={editMap[mod.id] ?? mod.hours_completed}
              onChangeHours={onChangeHours}
            />
          ))}
        {subject.modules.length === 0 && (
          <p className="text-muted text-center py-2 mb-0" style={{ fontSize: '0.85rem' }}>
            Nenhum módulo selecionado para esta turma.
          </p>
        )}
      </CCardBody>
    </CCard>
  )
}

// ==========================================
//  COMPONENT PRINCIPAL: ClassDetails
// ==========================================
const ClassDetails = () => {
  const { courseId, classId } = useParams()
  const navigate = useNavigate()
  const numClassId = Number(classId)
  const numCourseId = Number(courseId)

  // --- DATA ---
  const { data: classData, isLoading, error } = useClassDetails(numClassId)
  const { data: classSubjects } = useClassSubjects(numClassId)
  const updateClass = useUpdateCourseClass()
  const updateProgress = useUpdateClassProgress()
  const attemptScope = useAttemptScope()

  // --- STATE: Edição do header ---
  const [editingHeader, setEditingHeader] = useState(false)
  const [headerForm, setHeaderForm] = useState({ name: '', size: 25 })

  // --- STATE: Edição de progresso ---
  const [editingProgress, setEditingProgress] = useState(false)
  const [progressEdit, setProgressEdit] = useState({})

  // --- MEMOIZED: Totais globais ---
  // eslint-disable-next-line react-hooks/preserve-manual-memoization
  const globalStats = useMemo(() => {
    if (!classData?.subjects) return { totalHours: 0, completedHours: 0, pct: 0, totalModules: 0, completedModules: 0 }
    let totalH = 0, completedH = 0, totalM = 0, completedM = 0
    for (const s of classData.subjects) {
      totalH += s.total_hours
      completedH += s.completed_hours
      for (const m of s.modules) {
        totalM++
        if (m.is_completed) completedM++
      }
    }
    return {
      totalHours: totalH,
      completedHours: completedH,
      pct: totalH > 0 ? Math.round((completedH / totalH) * 100) : 0,
      totalModules: totalM,
      completedModules: completedM,
    }
    }, [classData?.subjects])

  // ==========================================
  //  HANDLERS: Header
  // ==========================================
  const startEditHeader = useCallback(() => {
    setHeaderForm({ name: classData.name, size: classData.size })
    setEditingHeader(true)
  }, [classData])

  const cancelEditHeader = () => setEditingHeader(false)

  const saveHeader = () => {
    const trimName = headerForm.name.trim()
    const size = Number.parseInt(headerForm.size, 10)
    if (!trimName || Number.isNaN(size) || size <= 0) return

    updateClass.mutate(
      { courseId: numCourseId, classId: numClassId, data: { name: trimName, size } },
      attemptScope.guard({
        onSuccess: () => {
          setEditingHeader(false)
          toast.success('Turma atualizada.')
        },
        onError: (error) => toast.error(getApiErrorMessage(error, 'Não foi possível guardar a turma. Tente novamente.')),
      })
    )
  }

  // ==========================================
  //  HANDLERS: Progresso
  // ==========================================
  const startEditProgress = useCallback(() => {
    // Preencher editMap com valores atuais
    const map = {}
    for (const s of classData.subjects || []) {
      for (const m of s.modules) {
        map[m.id] = m.hours_completed
      }
    }
    setProgressEdit(map)
    setEditingProgress(true)
  }, [classData])

  const cancelEditProgress = () => {
    setEditingProgress(false)
    setProgressEdit({})
  }

  const handleChangeHours = useCallback((moduleId, value) => {
    setProgressEdit(prev => ({ ...prev, [moduleId]: value }))
  }, [])

  const saveProgress = () => {
    // Filtrar apenas módulos cujo valor mudou
    const changes = []
    for (const s of classData.subjects || []) {
      for (const m of s.modules) {
        const newVal = progressEdit[m.id]
        if (newVal !== undefined && newVal !== m.hours_completed) {
          changes.push({ module_id: m.id, hours_completed: Math.max(0, Math.min(newVal, m.hours_total)) })
        }
      }
    }

    if (changes.length === 0) {
      setEditingProgress(false)
      return
    }

    updateProgress.mutate(
      { classId: numClassId, progress: changes },
      attemptScope.guard({
        onSuccess: () => {
          setEditingProgress(false)
          setProgressEdit({})
          toast.success('Progresso atualizado.')
        },
        onError: (error) => toast.error(getApiErrorMessage(error, 'Não foi possível atualizar o progresso. Tente novamente.')),
      })
    )
  }

  // ==========================================
  //  RENDER: Loading / Error
  // ==========================================
  if (isLoading) {
    return (
      <div className="p-4 text-center">
        <CSpinner color="primary" />
        <p className="text-muted mt-2">A carregar turma...</p>
      </div>
    )
  }

  if (error || !classData) {
    return (
      <div className="p-4">
        <div className="mb-3"><FeedbackBanner tone="danger">
          <strong>Erro:</strong> {getApiErrorMessage(error, 'Turma não encontrada.')}
        </FeedbackBanner></div>
        <CButton color="light" onClick={() => navigate(`/courses/${numCourseId}`)}>
          <CIcon icon={cilArrowLeft} className="me-1" /> Voltar ao Curso
        </CButton>
      </div>
    )
  }

  const yearLabel = `${classData.start_year}/${classData.end_year}`

  // ==========================================
  //  RENDER: Page
  // ==========================================
  return (
    <div className="p-4">
      <Breadcrumbs items={[
        { label: 'Cursos', to: '/courses' },
        { label: classData.course?.abbreviation || classData.course?.name || `Curso ${numCourseId}`, to: `/courses/${numCourseId}` },
        { label: classData.name },
      ]} />

      {/* ==== HEADER DA TURMA ==== */}
      <CCard className="mb-4 border-0 shadow-sm">
        <CCardBody>
          {editingHeader ? (
            /* --- MODO EDIÇÃO --- */
            <CRow className="g-3 align-items-end">
              <CCol md={5}>
                <label htmlFor="header-name" className="form-label fw-semibold">Nome da Turma</label>
                <CFormInput
                  id="header-name"
                  value={headerForm.name}
                  onChange={(e) => setHeaderForm(prev => ({ ...prev, name: e.target.value }))}
                  placeholder="Ex: TGEI 25/28"
                  autoFocus
                />
              </CCol>
              <CCol md={3}>
                <label htmlFor="header-size" className="form-label fw-semibold">Capacidade (alunos)</label>
                <CFormInput
                  id="header-size"
                  type="number"
                  min={1}
                  max={200}
                  value={headerForm.size}
                  onChange={(e) => setHeaderForm(prev => ({ ...prev, size: e.target.value }))}
                />
              </CCol>
              <CCol md={4} className="d-flex gap-2">
                <CButton color="primary" onClick={saveHeader} disabled={updateClass.isPending}>
                  {updateClass.isPending ? <CSpinner size="sm" /> : <CIcon icon={cilSave} className="me-1" />}
                  Guardar
                </CButton>
                <CButton color="light" onClick={cancelEditHeader} disabled={updateClass.isPending}>
                  <CIcon icon={cilX} />
                </CButton>
              </CCol>
            </CRow>
          ) : (
            /* --- MODO VISUALIZAÇÃO --- */
            <div className="d-flex justify-content-between align-items-start">
              <div>
                <div className="d-flex align-items-center gap-2 mb-2">
                  <h3 className="mb-0 fw-bold">{classData.name}</h3>
                  <CBadge color="primary" shape="rounded-pill">{yearLabel}</CBadge>
                  <CBadge color="secondary" shape="rounded-pill">
                    {formatGradeLevel(classData.grade_level)}
                  </CBadge>
                </div>
                {classData.course && (
                  <div className="d-flex align-items-center gap-1 mb-2 text-muted" style={{ fontSize: '0.9rem' }}>
                    <CIcon icon={cilBookmark} size="sm" />
                    <span>{classData.course.name}</span>
                    <CBadge color="light" className="text-dark ms-1">{classData.course.abbreviation}</CBadge>
                  </div>
                )}
                {/* --- STATS RÁPIDOS --- */}
                <div className="d-flex gap-4 mt-1" style={{ fontSize: '0.85rem' }}>
                  <div className="d-flex align-items-center gap-1 text-muted">
                    <CIcon icon={cilPeople} size="sm" />
                    <span>{classData.size} alunos</span>
                  </div>
                </div>
              </div>
              <div className="d-flex gap-2">
                <CButton color="light" size="sm" onClick={startEditHeader} title="Editar nome e capacidade">
                  <CIcon icon={cilPencil} className="me-1" />
                  Editar
                </CButton>
              </div>
            </div>
          )}
        </CCardBody>
      </CCard>

      {/* ==== RESUMO DISCIPLINAS & PROFESSORES (inline) ==== */}
      <CCard className="mb-4 border-0 shadow-sm">
        <CCardHeader className="bg-transparent d-flex justify-content-between align-items-center">
          <div className="d-flex align-items-center gap-2">
            <CIcon icon={cilSettings} className="text-primary" />
            <strong>Disciplinas &amp; Professores</strong>
          </div>
          <CButton
            color="primary"
            variant="outline"
            size="sm"
            onClick={() => navigate(`/courses/${numCourseId}/classes/${numClassId}/subjects`)}
          >
            Gerir
            <CIcon icon={cilChevronRight} size="sm" className="ms-1" />
          </CButton>
        </CCardHeader>
        <CCardBody className="py-2">
          {(classSubjects?.subjects || []).length === 0 ? (
            <p className="text-muted text-center mb-0 py-2">
              Nenhuma disciplina atribuída. Clique em &quot;Gerir&quot; para adicionar disciplinas e atribuir professores.
            </p>
          ) : (
            <div className="table-responsive">
              <table className="table table-sm table-hover mb-0 align-middle" style={{ fontSize: '0.9rem' }}>
                <thead>
                  <tr className="text-muted">
                    <th style={{ fontWeight: 600 }}>Disciplina</th>
                    <th style={{ fontWeight: 600 }}>Professor</th>
                    <th style={{ fontWeight: 600 }}>Módulos</th>
                  </tr>
                </thead>
                <tbody>
                  {classSubjects.subjects.map(s => {
                    const modules = s.modules || []
                    const selectedCount = modules.filter(module => module.selected).length
                    const jointOtherNames = (s.joint_group?.classes || [])
                      .filter(cls => cls.class_id !== numClassId)
                      .map(cls => cls.class_name)
                      .join(', ')
                    return (
                      <tr key={s.id}>
                        <td>
                          <div className="d-flex align-items-center gap-2">
                            <CIcon icon={cilBook} className="text-info" size="sm" />
                            <span className="fw-medium">{s.subject_name}</span>
                            {jointOtherNames && (
                              <CBadge
                                color="info"
                                title={`Aula conjunta com ${jointOtherNames}`}
                                aria-label={`Aula conjunta com ${jointOtherNames}`}
                              >
                                Conjunta
                              </CBadge>
                            )}
                          </div>
                        </td>
                        <td>
                          {s.teacher_name ? (
                            <span className="text-success">
                              <CIcon icon={cilCheckCircle} size="sm" className="me-1" />
                              {s.teacher_name}
                            </span>
                          ) : (
                            <span className="text-warning fst-italic">Sem professor</span>
                          )}
                        </td>
                        <td>{selectedCount}/{modules.length}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CCardBody>
      </CCard>

      {/* ==== SECÇÃO DE DISCIPLINAS + MÓDULOS ==== */}
      <CCard className="border-0 shadow-sm">
        <CCardHeader className="bg-transparent d-flex justify-content-between align-items-center">
          <div className="d-flex align-items-center gap-2">
            <CIcon icon={cilBook} className="text-info" />
            <strong>Progresso por Disciplina</strong>
          </div>
          {editingProgress ? (
            <div className="d-flex gap-1">
              <CButton color="primary" size="sm" onClick={saveProgress} disabled={updateProgress.isPending}>
                {updateProgress.isPending ? <CSpinner size="sm" /> : <CIcon icon={cilSave} size="sm" className="me-1" />}
                Guardar
              </CButton>
              <CButton color="light" size="sm" onClick={cancelEditProgress} disabled={updateProgress.isPending}>
                <CIcon icon={cilX} size="sm" />
              </CButton>
            </div>
          ) : (
            <CButton
              color="light"
              size="sm"
              onClick={startEditProgress}
              disabled={(classData.subjects || []).length === 0}
            >
              <CIcon icon={cilPencil} size="sm" className="me-1" />
              Editar Progresso
            </CButton>
          )}
        </CCardHeader>
        <CCardBody>
          {(classData.subjects || []).length === 0 ? (
            <p className="text-muted text-center mb-0">
              Nenhuma disciplina associada ao curso desta turma.
            </p>
          ) : (
            <>
              <div className="mb-4">
                <div className="d-flex justify-content-between align-items-center mb-2">
                  <strong style={{ fontSize: '0.9rem' }}>Progresso Global</strong>
                  <CBadge
                    shape="rounded-pill"
                    className="zen-badge-progress"
                    style={{ fontSize: '0.85rem', backgroundColor: getProgressColor(globalStats.pct) }}
                  >
                    {globalStats.pct}%
                  </CBadge>
                </div>
                <div
                  className="mb-1"
                  role="progressbar"
                  aria-label="Progresso global da turma"
                  aria-valuemin="0"
                  aria-valuemax="100"
                  aria-valuenow={Math.min(Math.max(Number(globalStats.pct) || 0, 0), 100)}
                  style={{ height: '12px', borderRadius: '6px', backgroundColor: 'var(--color-bg-muted)', overflow: 'hidden' }}
                >
                  <div
                    style={{
                      height: '100%',
                      width: `${Math.min(Math.max(Number(globalStats.pct) || 0, 0), 100)}%`,
                      backgroundColor: getProgressColor(globalStats.pct),
                      borderRadius: '6px',
                      transition: 'width 0.5s ease',
                    }}
                  />
                </div>
                <small className="text-muted">
                  {globalStats.completedHours} de {globalStats.totalHours} horas · {globalStats.completedModules} de {globalStats.totalModules} módulos concluídos
                </small>
              </div>
              {[...classData.subjects]
                .sort((a, b) => a.name.localeCompare(b.name))
                .map(subject => (
                  <SubjectCard
                    key={subject.id}
                    subject={subject}
                    isEditing={editingProgress}
                    editMap={progressEdit}
                    onChangeHours={handleChangeHours}
                  />
                ))}
            </>
          )}
        </CCardBody>
      </CCard>
    </div>
  )
}

export default ClassDetails
