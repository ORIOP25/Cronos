import React, { useMemo, useState } from 'react'
import PageHeader from '../components/PageHeader'
import { CAlert, CBadge, CCard, CCardBody, CCardHeader, CSpinner } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilBook, cilEducation } from '@coreui/icons'
import { useTeacherProgress } from '../hooks/useSchoolData'
import { useUser } from '@clerk/react'

function SubjectRow({ subject }) {
  const isLow = subject.overall_percentage < 50
  const barColor = isLow ? 'var(--brand-500)' : 'var(--rs-teal)'

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '10px 0',
        borderBottom: '1px solid var(--color-border-default)',
      }}
    >
      <div style={{ flex: 2, minWidth: 0 }}>
        <div
          style={{
            fontSize: '0.82rem',
            fontWeight: 600,
            color: 'var(--brand-950)',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          <CIcon icon={cilBook} className="me-1" style={{ opacity: 0.6 }} />
          {subject.subject_name}
        </div>
        <div style={{ fontSize: '0.68rem', color: 'var(--rs-muted)' }}>
          {subject.completed_hours}h / {subject.total_hours}h
        </div>
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div
            style={{
              flex: 1,
              height: 6,
              borderRadius: 3,
              background: 'var(--color-bg-surface-strong)',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${Math.min(subject.overall_percentage, 100)}%`,
                height: '100%',
                borderRadius: 3,
                background: barColor,
                transition: 'width 0.6s ease',
              }}
            />
          </div>
          <span
            style={{
              fontSize: '0.78rem',
              fontWeight: 600,
              color: isLow ? 'var(--brand-600)' : 'var(--rs-teal)',
              minWidth: 34,
              textAlign: 'right',
            }}
          >
            {subject.overall_percentage}%
          </span>
        </div>
      </div>
    </div>
  )
}

function ClassCard({ classData }) {
  const [expanded, setExpanded] = useState(true)
  const avg = useMemo(() => {
    if (!classData.subjects || classData.subjects.length === 0) return 0
    return Math.round(
      classData.subjects.reduce((s, p) => s + p.overall_percentage, 0) / classData.subjects.length
    )
  }, [classData.subjects])

  return (
    <CCard className="border-0 shadow-sm mb-3">
      <CCardHeader
        className="bg-light border-0 d-flex justify-content-between align-items-center"
        style={{ cursor: 'pointer' }}
        onClick={() => setExpanded((prev) => !prev)}
      >
        <div className="d-flex align-items-center gap-2">
          <CIcon icon={cilEducation} style={{ opacity: 0.7 }} />
          <div>
            <div className="fw-semibold" style={{ fontSize: '0.95rem' }}>
              {classData.class_name}
            </div>
            <div style={{ fontSize: '0.7rem', color: 'var(--rs-muted)' }}>
              {classData.course_name || '—'} · {classData.grade_level}º ano
            </div>
          </div>
        </div>
        <div className="d-flex align-items-center gap-2">
          <CBadge color={avg < 50 ? 'warning' : 'success'} className="px-2 py-1">
            Média: {avg}%
          </CBadge>
          <span style={{ fontSize: '0.75rem', color: 'var(--rs-muted)' }}>
            {expanded ? '▼' : '▶'}
          </span>
        </div>
      </CCardHeader>
      {expanded && (
        <CCardBody style={{ padding: '12px 20px' }}>
          {classData.subjects && classData.subjects.length > 0 ? (
            classData.subjects.map((subject) => (
              <SubjectRow key={subject.subject_id} subject={subject} />
            ))
          ) : (
            <div className="text-center py-3 text-muted" style={{ fontSize: '0.85rem' }}>
              Sem disciplinas assignadas nesta turma.
            </div>
          )}
        </CCardBody>
      )}
    </CCard>
  )
}

function MyProgress() {
  const { user } = useUser()
  const teacherId = user?.publicMetadata?.teacher_id
  const { data: progressData, isLoading, isError, error } = useTeacherProgress({
    enabled: Boolean(teacherId),
  })

  if (!teacherId) {
    return (
      <div className="p-4">
        <CAlert color="danger" className="mb-0">
          Conta de professor sem perfil associado. Contacte um admin para associar o perfil docente.
        </CAlert>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="p-4">
        <CCard className="border-0 shadow-sm">
          <CCardBody className="py-4 d-flex align-items-center gap-2 text-muted">
            <CSpinner size="sm" />
            A carregar o seu progresso curricular...
          </CCardBody>
        </CCard>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="p-4">
        <CAlert color="danger" className="mb-0">
          {error?.response?.status === 403
            ? 'Sem permissões para consultar o progresso curricular.'
            : 'Não foi possível carregar o progresso. Tente novamente em alguns minutos.'}
        </CAlert>
      </div>
    )
  }

  const classes = progressData || []

  return (
    <div className="p-4">
      <PageHeader preTitle="Professor" title={<span>Meu <span className="text-editorial">Progresso</span></span>} />
      <div className="d-flex justify-content-end mb-4">
        <CBadge color="info" className="px-3 py-2">
          {classes.length} turma{classes.length === 1 ? '' : 's'}
        </CBadge>
      </div>

      {classes.length === 0 ? (
        <CCard className="border-0 shadow-sm">
          <CCardBody className="text-center py-5 text-muted">
            <CIcon icon={cilEducation} style={{ fontSize: '2rem', opacity: 0.35 }} />
            <div className="mt-2">Não está assignado a nenhuma turma/disciplina.</div>
          </CCardBody>
        </CCard>
      ) : (
        classes.map((classData) => <ClassCard key={classData.class_id} classData={classData} />)
      )}
    </div>
  )
}

export default MyProgress
