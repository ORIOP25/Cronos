import React, { useMemo, useState } from 'react'
import PropTypes from 'prop-types'
import {
  CAlert,
  CBadge,
  CCard,
  CCardBody,
  CCardHeader,
  CCol,
  CFormLabel,
  CFormSelect,
  CProgress,
  CRow,
  CSpinner,
  CTable,
  CTableBody,
  CTableDataCell,
  CTableHead,
  CTableHeaderCell,
  CTableRow,
} from '@coreui/react'
import { useAuditGenerations, useAuditSummary } from '../hooks/useSchoolData'

function normalizePercent(value) {
  if (value == null || Number.isNaN(value)) return 0
  if (value < 0) return 0
  if (value > 100) return 100
  return value
}

function getIntegrityColor(duplicates) {
  if (duplicates <= 0) return 'success'
  return 'danger'
}

const AuditStatCard = ({ title, value, subtitle, color = 'secondary' }) => (
  <CCard className="h-100">
    <CCardBody>
      <div className="text-muted small mb-1">{title}</div>
      <div className="d-flex align-items-center gap-2">
        <div className="fs-4 fw-bold">{value}</div>
        <CBadge color={color}>{color.toUpperCase()}</CBadge>
      </div>
      {subtitle ? <div className="small text-muted mt-1">{subtitle}</div> : null}
    </CCardBody>
  </CCard>
)

const AuditDashboard = () => {
  const { data: generations = [], isLoading: loadingGenerations, error: generationsError } = useAuditGenerations()
  const [selectedGeneration, setSelectedGeneration] = useState('')
  const hasGenerations = generations.length > 0
  const effectiveGeneration = selectedGeneration || generations[0]?.generation_id || ''

  const {
    data: summary,
    isLoading: loadingSummary,
    error: summaryError,
  } = useAuditSummary(effectiveGeneration || undefined, { enabled: hasGenerations })

  const roomUsageTotal = useMemo(
    () => (summary?.room_type_usage ?? []).reduce((acc, item) => acc + item.blocks_count, 0),
    [summary],
  )

  if (loadingGenerations) {
    return (
      <div className="text-center py-5">
        <CSpinner />
      </div>
    )
  }

  if (generationsError) {
    return <CAlert color="danger">Não foi possível carregar as gerações para auditoria.</CAlert>
  }

  return (
    <div className="d-flex flex-column gap-3">
      <div className="d-flex justify-content-between align-items-end mb-3 flex-wrap gap-3">
        <div>
          <span className="zen-caps" style={{ color: 'var(--brand-600)' }}>Auditoria</span>
          <h1 className="text-display mt-2" style={{ fontSize: '3rem', color: 'var(--brand-950)' }}>
            Painel de <span className="text-editorial">Verificação</span>
          </h1>
        </div>
        <div className="luxury-line" style={{ width: '100px', marginBottom: '14px' }} />
      </div>
      <CCard>
        <CCardBody>
          <CRow className="g-3 align-items-end">
            <CCol md={8} lg={6}>
              <CFormLabel htmlFor="generation-select">Geração</CFormLabel>
              <CFormSelect
                id="generation-select"
                value={selectedGeneration}
                onChange={(event) => setSelectedGeneration(event.target.value)}
              >
                {!hasGenerations ? <option value="">Sem gerações disponíveis</option> : null}
                {!selectedGeneration && hasGenerations ? (
                  <option value="">Selecionar (mais recente: {generations[0].generation_id})</option>
                ) : null}
                {generations.map((item) => (
                  <option key={item.generation_id} value={item.generation_id}>
                    {item.generation_id} | blocos: {item.blocks_count} | {item.start_date ?? '—'} até {item.end_date ?? '—'}
                  </option>
                ))}
              </CFormSelect>
            </CCol>
          </CRow>
        </CCardBody>
      </CCard>

      {!hasGenerations ? (
        <CAlert color="info">
          Ainda não existem gerações ativas para auditoria nesta organização. Gere um horário e volte a esta página.
        </CAlert>
      ) : null}

      {hasGenerations && loadingSummary ? (
        <div className="text-center py-5">
          <CSpinner />
        </div>
      ) : null}

      {hasGenerations && summaryError ? (
        <CAlert color="danger">Não foi possível carregar as métricas da geração selecionada.</CAlert>
      ) : null}

      {summary ? (
        <>
          <CRow className="g-3">
            <CCol md={6} lg={3}>
              <AuditStatCard
                title="Blocos da Geração"
                value={summary.blocks_count}
                subtitle={`${summary.start_date ?? '—'} até ${summary.end_date ?? '—'}`}
                color="primary"
              />
            </CCol>
            <CCol md={6} lg={3}>
              <AuditStatCard
                title="Turmas Vazias (Semana Atual)"
                value={summary.classes_empty_week}
                subtitle={`${summary.classes_with_week_slots}/${summary.classes_total} com slots`}
                color={summary.classes_empty_week > 0 ? 'danger' : 'success'}
              />
            </CCol>
            <CCol md={6} lg={3}>
              <AuditStatCard
                title="Duplicados Professor"
                value={summary.duplicate_teacher_slots}
                subtitle="Mesmo professor+data+timeslot"
                color={getIntegrityColor(summary.duplicate_teacher_slots)}
              />
            </CCol>
            <CCol md={6} lg={3}>
              <AuditStatCard
                title="Duplicados Turma"
                value={summary.duplicate_class_slots}
                subtitle="Mesma turma+data+timeslot"
                color={getIntegrityColor(summary.duplicate_class_slots)}
              />
            </CCol>
          </CRow>

          <CRow className="g-3">
            <CCol lg={6}>
              <CCard className="h-100">
                <CCardHeader className="fw-semibold">Fairness Semanal</CCardHeader>
                <CCardBody>
                  <div className="mb-2">Spread (desvio padrão de slots por turma): <strong>{summary.weekly_fairness_spread}</strong></div>
                  <div className="small text-muted mb-2">
                    Min: {summary.week_slots_min} | Max: {summary.week_slots_max} | Média: {summary.week_slots_avg}
                  </div>
                  <CProgress
                    value={normalizePercent((summary.classes_with_week_slots / Math.max(1, summary.classes_total)) * 100)}
                    color={summary.classes_empty_week > 0 ? 'warning' : 'success'}
                  />
                  <div className="small text-muted mt-1">Cobertura semanal de turmas com aulas</div>
                </CCardBody>
              </CCard>
            </CCol>
            <CCol lg={6}>
              <CCard className="h-100">
                <CCardHeader className="fw-semibold">Carga Docente (Semana Atual)</CCardHeader>
                <CCardBody>
                  <div className="small text-muted mb-2">
                    Professores com slots: {summary.teachers_with_week_slots}
                  </div>
                  <div className="small text-muted">
                    Min: {summary.teacher_week_slots_min} | Max: {summary.teacher_week_slots_max} | Média: {summary.teacher_week_slots_avg}
                  </div>
                </CCardBody>
              </CCard>
            </CCol>
          </CRow>

          <CCard>
            <CCardHeader className="fw-semibold">Utilização por Tipo de Sala</CCardHeader>
            <CCardBody>
              <CTable responsive striped hover>
                <CTableHead>
                  <CTableRow>
                    <CTableHeaderCell>Tipo</CTableHeaderCell>
                    <CTableHeaderCell>Blocos</CTableHeaderCell>
                    <CTableHeaderCell>Percentagem</CTableHeaderCell>
                  </CTableRow>
                </CTableHead>
                <CTableBody>
                  {summary.room_type_usage.map((item) => {
                    const pct = roomUsageTotal > 0 ? (item.blocks_count / roomUsageTotal) * 100 : 0
                    return (
                      <CTableRow key={item.room_type}>
                        <CTableDataCell>{item.room_type}</CTableDataCell>
                        <CTableDataCell>{item.blocks_count}</CTableDataCell>
                        <CTableDataCell>{pct.toFixed(1)}%</CTableDataCell>
                      </CTableRow>
                    )
                  })}
                </CTableBody>
              </CTable>
            </CCardBody>
          </CCard>
        </>
      ) : null}
    </div>
  )
}

AuditStatCard.propTypes = {
  title: PropTypes.string.isRequired,
  value: PropTypes.oneOfType([PropTypes.number, PropTypes.string]).isRequired,
  subtitle: PropTypes.string,
  color: PropTypes.string,
}

export default AuditDashboard
