import { useMemo } from 'react'
import PageHeader from '../components/PageHeader'
import FeedbackBanner from '../components/FeedbackBanner'
import { CBadge, CCard, CCardBody, CSpinner } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilBook, cilEducation } from '@coreui/icons'
import { useCurrentMember } from '../features/members/data'
import { useTeacherProgress } from '../features/operations/data'

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
            fontSize: 'var(--cronos-text-body)',
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
        <div style={{ fontSize: 'var(--cronos-text-small)', color: 'var(--rs-muted)' }}>
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
              fontSize: 'var(--cronos-text-small)',
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
  const avg = useMemo(() => {
    if (!classData.subjects || classData.subjects.length === 0) return 0
    return Math.round(
      classData.subjects.reduce((s, p) => s + p.overall_percentage, 0) / classData.subjects.length
    )
  }, [classData.subjects])

  return (
    <details className="compact-disclosure">
      <summary>
        <div className="d-flex align-items-center gap-2">
          <CIcon icon={cilEducation} style={{ opacity: 0.7 }} />
          <div>
            <div className="fw-semibold" style={{ fontSize: 'var(--cronos-text-body)' }}>
              {classData.class_name}
            </div>
            <div style={{ fontSize: 'var(--cronos-text-small)', color: 'var(--rs-muted)' }}>
              {classData.course_name || '—'} · {classData.grade_level}º ano
            </div>
          </div>
        </div>
        <div className="d-flex align-items-center gap-2">
          <CBadge color={avg < 50 ? 'warning' : 'success'} className="px-2 py-1">
            Média: {avg}%
          </CBadge>
        </div>
      </summary>
        <div className="compact-disclosure__body">
          {classData.subjects && classData.subjects.length > 0 ? (
            classData.subjects.map((subject) => (
              <SubjectRow key={subject.subject_id} subject={subject} />
            ))
          ) : (
            <div className="text-center py-3 text-muted" style={{ fontSize: 'var(--cronos-text-small)' }}>
              Sem disciplinas atribuídas nesta turma.
            </div>
          )}
        </div>
    </details>
  )
}

function MyProgress() {
  const { data: currentMember } = useCurrentMember()
  const teacherId = currentMember?.teacher_id
  const { data: progressData, isLoading, isError, error } = useTeacherProgress({
    enabled: Boolean(teacherId),
  })

  if (!teacherId) {
    return (
      <div className="p-4">
        <FeedbackBanner tone="danger">
          Conta de professor sem perfil associado. Contacte a administração para associar o perfil docente.
        </FeedbackBanner>
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
        <FeedbackBanner tone="danger">
          {error?.response?.status === 403
            ? 'Sem permissões para consultar o progresso curricular.'
            : 'Não foi possível carregar o progresso. Tente novamente em alguns minutos.'}
        </FeedbackBanner>
      </div>
    )
  }

  const classes = progressData || []

  return (
    <div className="p-4">
      <PageHeader preTitle="Professor" title="Meu Progresso" />
      <div className="d-flex justify-content-end mb-4">
        <CBadge color="info" className="px-3 py-2">
          {classes.length} turma{classes.length === 1 ? '' : 's'}
        </CBadge>
      </div>

      {classes.length === 0 ? (
        <CCard className="border-0 shadow-sm">
          <CCardBody className="text-center py-5 text-muted">
            <CIcon icon={cilEducation} style={{ fontSize: '2rem', opacity: 0.35 }} />
            <div className="mt-2">Não está atribuído a nenhuma turma/disciplina.</div>
          </CCardBody>
        </CCard>
      ) : (
        <div className="compact-list">
          {classes.map((classData) => <ClassCard key={classData.class_id} classData={classData} />)}
        </div>
      )}
    </div>
  )
}

export default MyProgress
