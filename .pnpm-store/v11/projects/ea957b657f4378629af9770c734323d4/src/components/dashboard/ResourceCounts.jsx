import React from 'react'
import { CCol, CRow } from '@coreui/react'

function KpiSkeleton() {
  return (
    <CCol xs={4} sm={2} className="mb-3 text-center">
      <div style={{ width: 48, height: 28, margin: '0 auto 4px', borderRadius: 4, background: 'var(--color-bg-surface-strong)' }} />
      <div style={{ width: 64, height: 10, margin: '0 auto', borderRadius: 3, background: 'var(--color-bg-surface-strong)' }} />
    </CCol>
  )
}

function RoomsSkeleton() {
  return (
    <CCol xs={12} sm={2} className="mb-3">
      <div style={{ width: '100%', height: 12, borderRadius: 3, marginBottom: 6, background: 'var(--color-bg-surface-strong)' }} />
      <div style={{ width: '70%', height: 10, borderRadius: 3, background: 'var(--color-bg-surface-strong)' }} />
    </CCol>
  )
}

export default function ResourceCounts({ resources, isLoading }) {
  if (isLoading) {
    return (
      <div data-testid="resource-counts">
        <CRow className="align-items-center">
          <KpiSkeleton /><KpiSkeleton /><KpiSkeleton /><KpiSkeleton /><KpiSkeleton />
          <RoomsSkeleton />
        </CRow>
      </div>
    )
  }

  const kpis = [
    { key: 'teachers', label: 'Professores', value: resources?.teachers_count ?? 0 },
    { key: 'classes', label: 'Turmas', value: resources?.classes_count ?? 0 },
    { key: 'courses', label: 'Cursos', value: resources?.courses_count ?? 0 },
    { key: 'subjects', label: 'Disciplinas', value: resources?.subjects_count ?? 0 },
    { key: 'rooms', label: 'Salas', value: resources?.rooms_count ?? 0 },
  ]

  const roomsByType = resources?.rooms_by_type ?? {}
  const roomTypeLabels = { normal: 'Normal', lab: 'Lab', gym: 'Ginásio', art: 'Arte' }

  return (
    <div data-testid="resource-counts">
      <CRow className="align-items-center">
        {kpis.map((kpi) => (
          <CCol key={kpi.key} xs={4} sm={2} className="mb-3 text-center">
            <span
              data-testid={`resource-${kpi.key}`}
              className="text-display d-block"
              style={{ fontSize: '1.8rem', fontWeight: 700, color: 'var(--brand-800)', lineHeight: 1.2 }}
            >
              {kpi.value}
            </span>
            <small style={{ fontSize: '0.7rem', color: 'var(--rs-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              {kpi.label}
            </small>
          </CCol>
        ))}
        <CCol xs={12} sm={2} className="mb-3">
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--rs-muted)', marginBottom: 4 }}>
            Salas por tipo
          </div>
          <div style={{ fontSize: '0.72rem', color: 'var(--brand-800)', lineHeight: 1.6 }}>
            {Object.entries(roomsByType).length === 0
              ? '—'
              : Object.entries(roomsByType).map(([type, count], i) => (
                  <span key={type}>
                    {roomTypeLabels[type] || type}: {count}
                    {i < Object.keys(roomsByType).length - 1 ? ' · ' : ''}
                  </span>
                ))
            }
          </div>
        </CCol>
      </CRow>
    </div>
  )
}
