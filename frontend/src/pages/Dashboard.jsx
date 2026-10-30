import { useOrganization, useUser } from '@clerk/react'
import AnalyticsHeatmap from '../components/AnalyticsHeatmap'
import AlertBar from '../components/dashboard/AlertBar'
import ClassProgressOverview from '../components/dashboard/ClassProgressOverview'
import DashboardRankings from '../components/dashboard/DashboardRankings'
import DebtSummaryCard from '../components/dashboard/DebtSummaryCard'
import SchoolOverviewCard from '../components/dashboard/SchoolOverviewCard'
import WeeklyPulse from '../components/dashboard/WeeklyPulse'
import { useDashboard, useDashboardInsights } from '../features/operations/data'
import { PreparationDashboard } from '../features/dashboard/PreparationDashboard'
import PageHeader from '../components/PageHeader'
import StatePanel from '../components/StatePanel'
import { getApiErrorMessage } from '../utils/apiErrors'

export default function Dashboard() {
  const { organization } = useOrganization()
  const { user } = useUser()
  const { data, isLoading, isError, error } = useDashboard()
  // Insights load after the main payload, and only once the school is operational.
  const insightsQuery = useDashboardInsights({ enabled: data?.mode === 'OPERATIONAL' })
  const insights = insightsQuery.data

  const orgName = data?.organization_name || organization?.name || 'Escola'

  const currentDate = new Intl.DateTimeFormat('pt-PT', { dateStyle: 'long' }).format(new Date())
  const header = (
    <PageHeader
      title={user?.firstName ? `Olá, ${user.firstName}` : 'O dia na escola'}
      context={data?.organization_name || undefined}
      description={`Hoje, ${currentDate}.`}
    />
  )

  if (isError) {
    return (
      <div className="p-4">
        {header}
        <StatePanel
          state="error"
          title="Não foi possível carregar o painel"
          description={getApiErrorMessage(error, 'Tente novamente mais tarde.')}
        />
      </div>
    )
  }

  if (isLoading && !data) {
    return (
      <div className="p-4">
        {header}
        <StatePanel
          state="loading"
          title="A carregar o painel"
          description="A reunir a prontidão e o estado operacional da escola."
        />
      </div>
    )
  }

  if (data?.mode === 'PREPARATION') {
    return (
      <PreparationDashboard
        orgId={organization?.id}
        userId={user?.id}
        organizationName={orgName}
        foundationStatus={data.foundation_status}
        bases={data.bases}
        prevalidation={data.prevalidation}
        autoStartGuide={false}
      />
    )
  }

  if (data?.mode !== 'OPERATIONAL') {
    return (
      <StatePanel
        state="error"
        title="Não foi possível abrir o painel"
        description="Os dados do painel não estão disponíveis. Atualize a página e tente novamente."
      />
    )
  }

  return (
    <div className="p-4">
      {header}
      <div className="dashboard-stack">
        <AlertBar alerts={data?.alerts} currentWeek={insights?.weeks?.at(-1)} isLoading={isLoading} />
        {insightsQuery.isError ? (
          <StatePanel
            state="error"
            compact
            title="Não foi possível carregar as tendências"
            description={getApiErrorMessage(insightsQuery.error, 'Tente novamente mais tarde.')}
            action={<button type="button" className="btn btn-link" onClick={() => void insightsQuery.refetch()}>Tentar novamente</button>}
          />
        ) : insights ? (
          <WeeklyPulse weeks={insights.weeks ?? []} />
        ) : (
          <StatePanel state="loading" compact title="A calcular as tendências da semana" />
        )}
        <div className="dashboard-overview-grid">
          <DebtSummaryCard debts={data?.debts} debtWeeks={insights?.debt_weeks} progress={data?.class_progress} isLoading={isLoading || insightsQuery.isLoading} />
          <ClassProgressOverview progress={data?.class_progress} plannedMinutes={insights?.planned_minutes_to_date} isLoading={isLoading} />
        </div>
        {insights && <DashboardRankings insights={insights} progress={data?.class_progress} />}
        <div className="dashboard-overview-grid">
          <div className="zen-card">
            <div className="zen-card-header">
              <h3 className="mb-0 dashboard-card-title">Disponibilidade</h3>
            </div>
            <div className="zen-card-body">
              <AnalyticsHeatmap />
            </div>
          </div>
          <SchoolOverviewCard resources={data?.resources} health={data?.schedule_health} isLoading={isLoading} />
        </div>
      </div>
    </div>
  )
}
