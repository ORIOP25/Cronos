import React from 'react'
import { useNavigate } from 'react-router-dom'

function RowSkeleton() {
  return (
    <div className="d-flex align-items-center gap-3 py-2" style={{ borderBottom: '1px solid var(--color-border-default)' }}>
      <div style={{ flex: 2, height: 14, borderRadius: 3, background: 'var(--color-bg-surface-strong)' }} />
      <div style={{ flex: 1, height: 14, borderRadius: 3, background: 'var(--color-bg-surface-strong)' }} />
      <div style={{ flex: 1, height: 14, borderRadius: 3, background: 'var(--color-bg-surface-strong)' }} />
      <div style={{ flex: 1, height: 8, borderRadius: 4, background: 'var(--color-bg-surface-strong)' }} />
    </div>
  )
}

export default function ClassProgressOverview({ progress, isLoading }) {
  const navigate = useNavigate()

  if (isLoading) {
    return (
      <div data-testid="class-progress">
        <div className="zen-card">
          <div className="zen-card-header">
            <h3 className="mb-0" style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--brand-800)' }}>Progresso Curricular</h3>
          </div>
          <div className="zen-card-body">
            <RowSkeleton />
            <RowSkeleton />
            <RowSkeleton />
            <RowSkeleton />
          </div>
        </div>
      </div>
    )
  }

  if (!progress || progress.length === 0) {
    return (
      <div data-testid="class-progress">
        <div className="zen-card">
          <div className="zen-card-header">
            <h3 className="mb-0" style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--brand-800)' }}>Progresso Curricular</h3>
          </div>
          <div className="zen-card-body text-center py-4" data-testid="class-progress-empty">
            <p className="mb-0" style={{ color: 'var(--rs-muted)', fontSize: '0.85rem' }}>Sem dados de progresso. Comece por registar horas nas turmas.</p>
          </div>
        </div>
      </div>
    )
  }

  const avg = progress.length > 0
    ? Math.round(progress.reduce((s, p) => s + p.overall_percentage, 0) / progress.length)
    : 0

  return (
    <div data-testid="class-progress">
      <div className="zen-card">
        <div className="zen-card-header">
          <h3 className="mb-0" style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--brand-800)' }}>Progresso Curricular</h3>
          <span style={{ fontSize: '0.7rem', color: 'var(--rs-muted)' }}>
            Média: {avg}%
          </span>
        </div>
        <div className="zen-card-body" style={{ padding: '12px 20px' }}>
          {progress.map((p) => {
            const isLow = p.overall_percentage < 50
            const barColor = isLow ? 'var(--brand-500)' : 'var(--rs-teal)'
            return (
              <button
                key={p.class_id}
                data-testid="class-progress-row"
                onClick={() => navigate(`/courses/${p.course_id}/classes/${p.class_id}`)}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  padding: '10px 0',
                  border: 'none',
                  borderBottom: '1px solid var(--color-border-default)',
                  background: 'none',
                  cursor: 'pointer',
                  transition: 'background 0.15s ease',
                  textAlign: 'left',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--color-bg-surface-strong)' }}
                onMouseLeave={(e) => { e.currentTarget.style.background = 'none' }}
              >
                <div style={{ flex: 2, minWidth: 0 }}>
                  <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--brand-950)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {p.class_name}
                  </div>
                  <div style={{ fontSize: '0.68rem', color: 'var(--rs-muted)' }}>
                    {p.course_name || '—'} · {p.grade_level}º ano
                  </div>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div style={{
                      flex: 1,
                      height: 6,
                      borderRadius: 3,
                      background: 'var(--color-bg-surface-strong)',
                      overflow: 'hidden',
                    }}>
                      <div style={{
                        width: `${Math.min(p.overall_percentage, 100)}%`,
                        height: '100%',
                        borderRadius: 3,
                        background: barColor,
                        transition: 'width 0.6s ease',
                      }} />
                    </div>
                    <span style={{
                      fontSize: '0.78rem',
                      fontWeight: 600,
                      color: isLow ? 'var(--brand-600)' : 'var(--rs-teal)',
                      minWidth: 34,
                      textAlign: 'right',
                    }}>
                      {p.overall_percentage}%
                    </span>
                  </div>
                </div>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
