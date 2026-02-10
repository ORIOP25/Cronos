import React, { useState, useMemo, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  CCard, CCardBody, CCardHeader, CCol, CRow, CButton, CAlert,
  CBadge, CSpinner, CFormInput, CProgress, CProgressBar,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import {
  cilArrowLeft, cilPencil, cilSave, cilX,
  cilPeople, cilBook, cilCheckCircle, cilClock,
  cilBookmark,
} from '@coreui/icons'

import {
  useClassDetails,
  useUpdateEntity,
  useUpdateClassProgress,
} from '../hooks/useSchoolData'

// ==========================================
//  HELPERS
// ==========================================

/** Cor da barra de progresso conforme percentagem */
const getProgressColor = (pct) => {
  if (pct >= 100) return 'success'
  if (pct >= 60) return 'info'
  if (pct >= 30) return 'warning'
  return 'danger'
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

// ==========================================
//  SUB-COMPONENT: Linha de módulo com progresso editável
// ==========================================
const ModuleRow = ({ module, isEditing, editValue, onChangeHours }) => {
  const pct = module.hours_total > 0
    ? Math.round(((isEditing ? editValue : module.hours_completed) / module.hours_total) * 100)
    : 0
  const displayPct = Math.min(pct, 100)
  const displayHours = isEditing ? editValue : module.hours_completed

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
            <CFormInput
              type="number"
              min={0}
              max={module.hours_total}
              value={editValue}
              onChange={(e) => onChangeHours(module.id, parseInt(e.target.value, 10) || 0)}
              size="sm"
              style={{ width: '70px', textAlign: 'center' }}
            />
          ) : (
            <span className="text-muted" style={{ fontSize: '0.85rem', whiteSpace: 'nowrap' }}>
              {displayHours}/{module.hours_total}h
            </span>
          )}
          <CBadge
            color={getProgressColor(displayPct)}
            shape="rounded-pill"
            style={{ minWidth: '48px', textAlign: 'center' }}
          >
            {displayPct}%
          </CBadge>
        </div>
      </div>
      <CProgress thin className="mt-1">
        <CProgressBar color={getProgressColor(displayPct)} value={displayPct} />
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
            <RoomBadge type={subject.required_room_type} />
          </div>
          <div className="d-flex align-items-center gap-2">
            <span className="text-muted" style={{ fontSize: '0.85rem' }}>
              {subject.completed_hours}/{subject.total_hours}h
            </span>
            <CBadge
              color={getProgressColor(pct)}
              shape="rounded-pill"
              style={{ minWidth: '48px', textAlign: 'center' }}
            >
              {pct}%
            </CBadge>
          </div>
        </div>
        <CProgress thin className="mt-2">
          <CProgressBar color={getProgressColor(pct)} value={Math.min(pct, 100)} />
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
  const updateClass = useUpdateEntity('classes')
  const updateProgress = useUpdateClassProgress()

  // --- STATE: Edição do header ---
  const [editingHeader, setEditingHeader] = useState(false)
  const [headerForm, setHeaderForm] = useState({ name: '', size: 25 })

  // --- STATE: Edição de progresso ---
  const [editingProgress, setEditingProgress] = useState(false)
  const [progressEdit, setProgressEdit] = useState({}) // { moduleId: hours }

  // --- MEMOIZED: Totais globais ---
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
    const size = parseInt(headerForm.size, 10)
    if (!trimName || isNaN(size) || size <= 0) return

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
      {/* ---- BREADCRUMB ---- */}
      <div className="mb-3 d-flex align-items-center gap-1" style={{ fontSize: '0.9rem' }}>
        <Link to="/courses" className="text-decoration-none text-muted">Cursos</Link>
        <span className="text-muted">/</span>
        <Link to={`/courses/${numCourseId}`} className="text-decoration-none text-muted">
          {classData.course?.abbreviation || classData.course?.name || `Curso ${numCourseId}`}
        </Link>
        <span className="text-muted">/</span>
        <span className="fw-medium text-dark">{classData.name}</span>
      </div>

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
                <label className="form-label fw-semibold">Nome da Turma</label>
                <CFormInput
                  value={headerForm.name}
                  onChange={(e) => setHeaderForm(prev => ({ ...prev, name: e.target.value }))}
                  placeholder="Ex: TGEI 25/28"
                  autoFocus
                />
              </CCol>
              <CCol md={3}>
                <label className="form-label fw-semibold">Capacidade (alunos)</label>
                <CFormInput
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
              <CButton color="light" size="sm" onClick={startEditHeader} title="Editar nome e capacidade">
                <CIcon icon={cilPencil} className="me-1" />
                Editar
              </CButton>
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
                color={getProgressColor(globalStats.pct)}
                shape="rounded-pill"
                style={{ fontSize: '0.85rem' }}
              >
                {globalStats.pct}%
              </CBadge>
            </div>
            <CProgress className="mb-1" style={{ height: '12px' }}>
              <CProgressBar
                color={getProgressColor(globalStats.pct)}
                value={Math.min(globalStats.pct, 100)}
                animated={globalStats.pct > 0 && globalStats.pct < 100}
              />
            </CProgress>
            <small className="text-muted">
              {globalStats.completedHours} de {globalStats.totalHours} horas · {globalStats.completedModules} de {globalStats.totalModules} módulos concluídos
            </small>
          </CCardBody>
        </CCard>
      )}

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
          {!editingProgress ? (
            <CButton
              color="light"
              size="sm"
              onClick={startEditProgress}
              disabled={(classData.subjects || []).length === 0}
            >
              <CIcon icon={cilPencil} size="sm" className="me-1" />
              Editar Progresso
            </CButton>
          ) : (
            <div className="d-flex gap-1">
              <CButton color="primary" size="sm" onClick={saveProgress} disabled={updateProgress.isPending}>
                {updateProgress.isPending ? <CSpinner size="sm" /> : <CIcon icon={cilSave} size="sm" className="me-1" />}
                Guardar
              </CButton>
              <CButton color="light" size="sm" onClick={cancelEditProgress} disabled={updateProgress.isPending}>
                <CIcon icon={cilX} size="sm" />
              </CButton>
            </div>
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