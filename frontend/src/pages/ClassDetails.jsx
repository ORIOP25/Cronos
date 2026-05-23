import React, { useState, useMemo, useCallback } from 'react'
import PropTypes from 'prop-types'
import { useParams, useNavigate } from 'react-router-dom'
import {
  CCard, CCardBody, CCardHeader, CCol, CRow, CButton, CAlert,
  CBadge, CSpinner, CFormInput, CProgress, CProgressBar,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import {
  cilArrowLeft, cilPencil, cilSave, cilX,
  cilPeople, cilBook, cilCheckCircle, cilClock,
  cilBookmark, cilChevronRight, cilSettings,
} from '@coreui/icons'

import {
  useClassDetails,
  useUpdateEntity,
  useUpdateClassProgress,
  useClassSubjects,
} from '../hooks/useSchoolData'
import Breadcrumbs from '../components/Breadcrumbs'

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

/** Badge de tipo de sala */
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

RoomBadge.propTypes = {
  type: PropTypes.string.isRequired,
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

ModuleRow.propTypes = {
  module: PropTypes.shape({
    id: PropTypes.number.isRequired,
    name: PropTypes.string.isRequired,
    code: PropTypes.string,
    hours_total: PropTypes.number.isRequired,
    hours_completed: PropTypes.number.isRequired,
    is_completed: PropTypes.bool,
  }).isRequired,
  isEditing: PropTypes.bool.isRequired,
  editValue: PropTypes.number.isRequired,
  onChangeHours: PropTypes.func.isRequired,
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
            <RoomBadge type={subject.required_room_type} />
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
        {subject.modules
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
            Nenhum módulo definido para esta disciplina.
          </p>
        )}
      </CCardBody>
    </CCard>
  )
}

SubjectCard.propTypes = {
  subject: PropTypes.shape({
    id: PropTypes.number.isRequired,
    name: PropTypes.string.isRequired,
    overall_percentage: PropTypes.number.isRequired,
    required_room_type: PropTypes.string,
    completed_hours: PropTypes.number.isRequired,
    total_hours: PropTypes.number.isRequired,
    modules: PropTypes.arrayOf(PropTypes.object).isRequired,
  }).isRequired,
  isEditing: PropTypes.bool.isRequired,
  editMap: PropTypes.objectOf(PropTypes.number).isRequired,
  onChangeHours: PropTypes.func.isRequired,
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
  const updateClass = useUpdateEntity('classes')
  const updateProgress = useUpdateClassProgress()

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
      { id: numClassId, name: trimName, size },
      { onSuccess: () => setEditingHeader(false) }
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
      { onSuccess: () => { setEditingProgress(false); setProgressEdit({}) } }
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
        <CAlert color="danger">
          <strong>Erro:</strong> {error?.response?.data?.detail || 'Turma não encontrada.'}
        </CAlert>
        <CButton color="light" onClick={() => navigate(`/courses/${numCourseId}`)}>
          <CIcon icon={cilArrowLeft} className="me-1" /> Voltar ao Curso
        </CButton>
      </div>
    )
  }

  const gradeLabels = { 10: '10.º ano', 11: '11.º ano', 12: '12.º ano' }
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

      {/* ---- ALERTAS ---- */}
      {updateClass.isError && (
        <CAlert color="danger" dismissible onClose={() => updateClass.reset()}>
          <strong>Erro ao atualizar turma:</strong>{' '}
          {updateClass.error?.response?.data?.detail || 'Ocorreu um erro.'}
        </CAlert>
      )}
      {updateProgress.isError && (
        <CAlert color="danger" dismissible onClose={() => updateProgress.reset()}>
          <strong>Erro ao atualizar progresso:</strong>{' '}
          {updateProgress.error?.response?.data?.detail || 'Ocorreu um erro.'}
        </CAlert>
      )}

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
                    {gradeLabels[classData.grade_level] || `${classData.grade_level}.º ano`}
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
                  <div className="d-flex align-items-center gap-1 text-muted">
                    <CIcon icon={cilClock} size="sm" />
                    <span>{globalStats.completedHours}/{globalStats.totalHours}h</span>
                  </div>
                  <div className="d-flex align-items-center gap-1 text-muted">
                    <CIcon icon={cilCheckCircle} size="sm" />
                    <span>{globalStats.completedModules}/{globalStats.totalModules} módulos</span>
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

      {/* ==== BARRA GLOBAL DE PROGRESSO ==== */}
      {globalStats.totalHours > 0 && (
        <CCard className="mb-4 border-0 shadow-sm">
          <CCardBody className="py-3">
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
            {/* Barra nativa — substitui CProgress/CProgressBar que não renderizava */}
            <div
              className="mb-1"
              style={{ height: '12px', borderRadius: '6px', backgroundColor: 'var(--color-bg-muted)', overflow: 'hidden' }}
            >
              <div
                style={{
                  height: '100%',
                  width: `${Math.min(Number(globalStats.pct) || 0, 100)}%`,
                  backgroundColor: getProgressColor(globalStats.pct),
                  borderRadius: '6px',
                  transition: 'width 0.5s ease',
                }}
              />
            </div>
            <small className="text-muted">
              {globalStats.completedHours} de {globalStats.totalHours} horas · {globalStats.completedModules} de {globalStats.totalModules} módulos concluídos
            </small>
          </CCardBody>
        </CCard>
      )}

      {/* ==== RESUMO DISCIPLINAS & PROFESSORES (inline) ==== */}
      <CCard className="mb-4 border-0 shadow-sm">
        <CCardHeader className="bg-transparent d-flex justify-content-between align-items-center">
          <div className="d-flex align-items-center gap-2">
            <CIcon icon={cilSettings} className="text-primary" />
            <strong>Disciplinas &amp; Professores</strong>
            <CBadge color="primary" shape="rounded-pill">
              {classSubjects?.subjects?.length || 0}
            </CBadge>
            {(classSubjects?.subjects || []).some(s => !s.teacher_id) && (
              <CBadge color="warning" shape="rounded-pill">
                {classSubjects.subjects.filter(s => !s.teacher_id).length} sem professor
              </CBadge>
            )}
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
              Nenhuma disciplina atribuída. Clique em "Gerir" para adicionar disciplinas e atribuir professores.
            </p>
          ) : (
            <div className="table-responsive">
              <table className="table table-sm table-hover mb-0 align-middle" style={{ fontSize: '0.9rem' }}>
                <thead>
                  <tr className="text-muted">
                    <th style={{ fontWeight: 600 }}>Disciplina</th>
                    <th style={{ fontWeight: 600 }}>Professor</th>
                  </tr>
                </thead>
                <tbody>
                  {classSubjects.subjects.map(s => (
                    <tr key={s.id}>
                      <td>
                        <div className="d-flex align-items-center gap-2">
                          <CIcon icon={cilBook} className="text-info" size="sm" />
                          <span className="fw-medium">{s.subject_name}</span>
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
                    </tr>
                  ))}
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
            <CBadge color="info" shape="rounded-pill">
              {classData.subjects?.length || 0}
            </CBadge>
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
            classData.subjects
              .sort((a, b) => a.name.localeCompare(b.name))
              .map(subject => (
                <SubjectCard
                  key={subject.id}
                  subject={subject}
                  isEditing={editingProgress}
                  editMap={progressEdit}
                  onChangeHours={handleChangeHours}
                />
              ))
          )}
        </CCardBody>
      </CCard>
    </div>
  )
}

export default ClassDetails