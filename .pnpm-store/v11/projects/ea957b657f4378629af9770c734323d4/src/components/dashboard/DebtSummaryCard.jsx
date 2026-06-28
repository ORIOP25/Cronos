import React from 'react'
import { useNavigate } from 'react-router-dom'

export default function DebtSummaryCard({ debts, isLoading }) {
  const navigate = useNavigate()

  if (isLoading) {
    return (
      <div data-testid="debt-summary">
        <div className="zen-card">
          <div className="zen-card-header">
            <h3 className="mb-0" style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--brand-800)' }}>Dívidas de Horas</h3>
          </div>
          <div className="zen-card-body text-center py-3">
            <div style={{ width: 64, height: 28, margin: '0 auto', borderRadius: 4, background: 'var(--color-bg-surface-strong)' }} />
          </div>
        </div>
      </div>
    )
  }

  const hasDebt = (debts?.total_hours_owed ?? 0) > 0
  const accentColor = hasDebt ? 'var(--brand-500)' : 'var(--rs-teal)'

  return (
    <div data-testid="debt-summary">
      <div className="zen-card">
        <div className="zen-card-header">
          <h3 className="mb-0" style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--brand-800)' }}>Dívidas de Horas</h3>
        </div>
        <div className="zen-card-body" style={{ padding: '20px' }}>
          <div className="d-flex justify-content-center gap-4 mb-3">
            <div className="text-center">
              <span
                className="text-display d-block"
                style={{ fontSize: '2rem', fontWeight: 700, color: accentColor, lineHeight: 1 }}
              >
                {debts?.total_hours_owed ?? 0}h
              </span>
              <small style={{ fontSize: '0.65rem', color: 'var(--rs-muted)', textTransform: 'uppercase' }}>
                horas em dívida
              </small>
            </div>
            <div className="text-center">
              <span
                className="text-display d-block"
                style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--brand-800)', lineHeight: 1 }}
              >
                {debts?.total_gaps ?? 0}
              </span>
              <small style={{ fontSize: '0.65rem', color: 'var(--rs-muted)', textTransform: 'uppercase' }}>
                gaps
              </small>
            </div>
          </div>
          <div style={{ fontSize: '0.72rem', color: 'var(--rs-muted)', textAlign: 'center', marginBottom: 12 }}>
            {debts?.affected_classes_count ?? 0} turmas afetadas
            {(debts?.total_hours_owed_overdue ?? 0) > 0 && (
              <> · <span style={{ color: 'var(--rs-deep)' }}>{debts?.total_hours_owed_overdue}h vencidas</span></>
            )}
          </div>
          <div className="text-center">
            <button
              onClick={() => navigate('/absences?view=debts')}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--brand-600)',
                fontSize: '0.8rem',
                fontWeight: 500,
                cursor: 'pointer',
                textDecoration: 'underline',
              }}
            >
              Ver detalhes →
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
