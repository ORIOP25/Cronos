import { useNavigate } from 'react-router-dom'
import { CAlert } from '@coreui/react'
import AnalyticsHeatmap from '../components/AnalyticsHeatmap'
import AlertBar from '../components/dashboard/AlertBar'
import ResourceCounts from '../components/dashboard/ResourceCounts'
import ScheduleHealthCard from '../components/dashboard/ScheduleHealthCard'
import ClassProgressOverview from '../components/dashboard/ClassProgressOverview'
import DebtSummaryCard from '../components/dashboard/DebtSummaryCard'
import QuickActions from '../components/dashboard/QuickActions'
import { useDashboard } from '../features/operations/data'
import PageHeader from '../components/PageHeader'
import { getApiErrorMessage } from '../utils/apiErrors'

const Dashboard = () => {
  const { data, isLoading, isError, error } = useDashboard()
  const navigate = useNavigate()

  // ── Header ──────────────────────────────────────
  const header = (
    <PageHeader preTitle="Visão Geral" title="Painel de Controlo" />
  )

  if (isError) {
    return (
      <div className="zen-reveal">
        {header}
        <CAlert color="danger" dismissible>
          Erro ao carregar o dashboard: {getApiErrorMessage(error, 'Tente novamente mais tarde.')}
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

      {/* Draft banner: mostra-se apenas se existir um rascunho pendente */}
      {!isLoading && (data?.alerts?.pending_drafts ?? 0) > 0 && (
        <div className="zen-stagger-1 mt-3 mb-1">
          <CAlert
            color="warning"
            className="d-flex align-items-center justify-content-between py-2 px-3 mb-0"
            style={{
              background: 'var(--color-bg-surface)',
              border: '1px solid var(--brand-500)',
              borderLeft: '4px solid var(--brand-500)',
              color: 'var(--brand-600)',
              fontSize: '0.85rem',
              borderRadius: 8,
            }}
          >
            <span>
              Existe <strong>1 rascunho</strong> de horário pendente. Reveja-o para garantir que as alterações não se perdem.
            </span>
            <button
              onClick={() => navigate('/schedules?tab=drafts')}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--brand-800)',
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
                textDecoration: 'underline',
                whiteSpace: 'nowrap',
              }}
            >
              Rever rascunho →
            </button>
          </CAlert>
        </div>
      )}

      {/* ZONA 2: Progresso Curricular (esq) | Dívidas + Recursos (dir) */}
      <div className="row mt-4">
        <div className="col-lg-6 mb-4 zen-stagger-2">
          <ClassProgressOverview progress={data?.class_progress} isLoading={isLoading} />
        </div>
        <div className="col-lg-6">
          <div className="zen-stagger-3 mb-4">
            <DebtSummaryCard debts={data?.debts} isLoading={isLoading} />
          </div>
          <div className="zen-stagger-4 mb-4">
            <div className="zen-card">
              <div className="zen-card-header">
                <h3 className="mb-0" style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--brand-800)' }}>
                  Visão de Recursos
                </h3>
              </div>
              <div className="zen-card-body">
                <ResourceCounts resources={data?.resources} isLoading={isLoading} />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="zen-stagger-5 mb-4">
        <ScheduleHealthCard health={data?.schedule_health} isLoading={isLoading} />
      </div>

      {/* ZONA 3: AnalyticsHeatmap (full width) */}
      <div className="zen-stagger-5 mb-4">
        <div className="zen-card">
          <div className="zen-card-header">
            <h3 className="mb-0" style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--brand-800)' }}>
              Raio-X de Disponibilidade
            </h3>
          </div>
          <div className="zen-card-body">
            <AnalyticsHeatmap />
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
