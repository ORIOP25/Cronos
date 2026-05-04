import React from 'react'
import { CAlert } from '@coreui/react'
import AnalyticsHeatmap from '../components/AnalyticsHeatmap'
import { AlertBar, ResourceCounts, ScheduleHealthCard, ClassProgressOverview, DebtSummaryCard, QuickActions } from '../components/dashboard'
import { useDashboard } from '../hooks/useSchoolData'

const Dashboard = () => {
  const { data, isLoading, isError, error } = useDashboard()

  // ── Header ──────────────────────────────────────
  const header = (
    <div className="d-flex justify-content-between align-items-end mb-5">
      <div>
        <span className="zen-caps" style={{ color: 'var(--brand-600)' }}>Visão Geral</span>
        <h1 className="text-display mt-2" style={{ fontSize: '3rem', color: 'var(--brand-950)' }}>
          Painel de <span className="text-editorial">Controlo</span>
        </h1>
      </div>
      <div className="luxury-line" style={{ width: '100px', marginBottom: '14px' }} />
    </div>
  )

  if (isError) {
    return (
      <div className="zen-reveal">
        {header}
        <CAlert color="danger" dismissible>
          Erro ao carregar o dashboard: {error?.message || 'Tente novamente mais tarde.'}
        </CAlert>
      </div>
    )
  }

  return (
    <div className="zen-reveal">
      {header}

      {/* ZONA 1: AlertBar */}
      <div className="zen-stagger-1">
        <AlertBar alerts={data?.alerts} isLoading={isLoading} />
      </div>

      {/* ZONA 2: ScheduleHealth + ClassProgress */}
      <div className="row mt-4">
        <div className="col-lg-6 mb-4 zen-stagger-2">
          <ScheduleHealthCard health={data?.schedule_health} isLoading={isLoading} />
        </div>
        <div className="col-lg-6 mb-4 zen-stagger-3">
          <ClassProgressOverview progress={data?.class_progress} isLoading={isLoading} />
        </div>
      </div>

      {/* ZONA 3: DebtSummary + ResourceCounts (left) + Heatmap (right) */}
      <div className="row">
        <div className="col-lg-6 mb-4">
          <div className="zen-stagger-4 mb-4">
            <DebtSummaryCard debts={data?.debts} isLoading={isLoading} />
          </div>
          <div className="zen-stagger-5">
            <div className="zen-card">
              <div className="zen-card-body">
                <ResourceCounts resources={data?.resources} isLoading={isLoading} />
              </div>
            </div>
          </div>
        </div>
        <div className="col-lg-6 mb-4 zen-stagger-6">
          <div className="zen-card">
            <div className="zen-card-header">
              <div className="d-flex align-items-center gap-2">
                <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--brand-500)' }} />
                <h3 className="mb-0" style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--brand-800)' }}>
                  Raio-X de Disponibilidade
                </h3>
              </div>
              <span className="text-muted" style={{ fontSize: '0.7rem' }}>Atualizado em tempo real</span>
            </div>
            <div className="zen-card-body">
              <AnalyticsHeatmap />
            </div>
          </div>
        </div>
      </div>

      {/* ZONA 4: QuickActions */}
      {data?.alerts && (
        <div className="zen-stagger-6 mt-2 mb-4">
          <QuickActions alerts={data.alerts} />
        </div>
      )}
    </div>
  )
}

export default Dashboard
