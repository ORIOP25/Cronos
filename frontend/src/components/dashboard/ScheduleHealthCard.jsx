import React from 'react'
import { useNavigate } from 'react-router-dom'
import { CButton } from '@coreui/react'

function getColor(value) {
  if (value === 0) return 'var(--rs-teal)'
  return 'var(--rs-deep)'
}

function MetricSkeleton() {
  return (
    <div className="col-6 col-md-4 mb-3 text-center">
      <div style={{ width: 40, height: 24, margin: '0 auto 4px', borderRadius: 4, background: 'var(--color-bg-surface-strong)' }} />
      <div style={{ width: 80, height: 9, margin: '0 auto', borderRadius: 3, background: 'var(--color-bg-surface-strong)' }} />
    </div>
  )
}

export default function ScheduleHealthCard({ health, isLoading }) {
  const navigate = useNavigate()

  if (isLoading) {
    return (
      <div data-testid="schedule-health">
        <div className="zen-card">
          <div className="zen-card-header">
            <h3 className="mb-0" style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--brand-800)' }}>Saúde do Horário</h3>
          </div>
          <div className="zen-card-body">
            <div className="row">
              <MetricSkeleton /><MetricSkeleton /><MetricSkeleton />
              <MetricSkeleton /><MetricSkeleton /><MetricSkeleton />
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (!health) {
    return (
      <div data-testid="schedule-health">
        <div className="zen-card">
          <div className="zen-card-header">
            <h3 className="mb-0" style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--brand-800)' }}>Saúde do Horário</h3>
          </div>
          <div className="zen-card-body text-center py-4" data-testid="schedule-health-empty">
            <p className="mb-3" style={{ color: 'var(--rs-muted)', fontSize: '0.9rem' }}>Nenhum horário gerado.</p>
            <CButton
              color="primary"
              variant="outline"
              size="sm"
              style={{
                borderColor: 'var(--brand-600)',
                color: 'var(--brand-800)',
              }}
              onClick={() => navigate('/schedules?action=new')}
            >
              Criar o primeiro
            </CButton>
          </div>
        </div>
      </div>
    )
  }

  const metrics = [
    { label: 'Turmas sem aula', value: health.classes_empty_week, alert: health.classes_empty_week > 0 },
    { label: 'Média slots/turma', value: health.week_slots_avg, alert: false },
    { label: 'Conflitos professor', value: health.duplicate_teacher_slots, alert: health.duplicate_teacher_slots > 0 },
    { label: 'Média slots/professor', value: health.teacher_week_slots_avg, alert: false },
    { label: 'Equidade (spread)', value: health.weekly_fairness_spread, alert: false },
    { label: 'Conflitos turma', value: health.duplicate_class_slots, alert: health.duplicate_class_slots > 0 },
  ]

  return (
    <div data-testid="schedule-health">
      <div className="zen-card">
        <div className="zen-card-header">
          <h3 className="mb-0" style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--brand-800)' }}>Saúde do Horário</h3>
        </div>
        <div className="zen-card-body">
          <div className="row">
            {metrics.map((m) => (
              <div key={m.label} className="col-6 col-md-4 mb-3 text-center">
                <span
                  className="text-display d-block"
                  style={{
                    fontSize: '1.5rem',
                    fontWeight: 700,
                    color: m.alert ? 'var(--rs-deep)' : 'var(--brand-800)',
                    lineHeight: 1.2,
                  }}
                >
                  {typeof m.value === 'number' ? m.value : '—'}
                </span>
                <small style={{
                  fontSize: '0.65rem',
                  color: m.alert ? 'var(--rs-deep)' : 'var(--rs-muted)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                }}>
                  {m.label}
                </small>
              </div>
            ))}
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--rs-muted)', textAlign: 'center', marginTop: 8 }}>
            {health.blocks_count} blocos no total · Geração #{health.generation_id?.slice(0, 12)}...
          </div>
        </div>
      </div>
    </div>
  )
}
