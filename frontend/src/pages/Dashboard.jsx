import { useOrganization, useUser } from '@clerk/react'
import AnalyticsHeatmap from '../components/AnalyticsHeatmap'
import AlertBar from '../components/dashboard/AlertBar'
import ResourceCounts from '../components/dashboard/ResourceCounts'
import ScheduleHealthCard from '../components/dashboard/ScheduleHealthCard'
import ClassProgressOverview from '../components/dashboard/ClassProgressOverview'
import DebtSummaryCard from '../components/dashboard/DebtSummaryCard'
import { useDashboard } from '../features/operations/data'
import { PreparationDashboard } from '../features/dashboard/PreparationDashboard'
import PageHeader from '../components/PageHeader'
import StatePanel from '../components/StatePanel'
import { getApiErrorMessage } from '../utils/apiErrors'

export default function Dashboard() {
  const { organization } = useOrganization()
  const { user } = useUser()
  const { data, isLoading, isError, error } = useDashboard()

  const orgName = data?.organization_name || organization?.name || 'Escola'

  const currentDate = new Intl.DateTimeFormat('pt-PT', { dateStyle: 'long' }).format(new Date())
  const header = (
    <PageHeader
      preTitle="Operação Diária"
      title="Painel de Controlo Operacional"
      context={data?.organization_name || undefined}
      description={`Hoje, ${currentDate}.`}
    />
  )

  if (isError) {
    return (
      <div>
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
      <div>
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
    <div>
      {header}
      <div className="mb-4">
        <AlertBar alerts={data?.alerts} health={data?.schedule_health} isLoading={isLoading} />
      </div>
      <div className="mb-4">
        <ScheduleHealthCard health={data?.schedule_health} isLoading={isLoading} />
      </div>
      <div className="mb-4">
        <ClassProgressOverview progress={data?.class_progress} isLoading={isLoading} />
      </div>
      <div className="dashboard-secondary-grid mb-4">
        <DebtSummaryCard debts={data?.debts} isLoading={isLoading} />
        <div className="zen-card">
          <div className="zen-card-header">
            <h3 className="mb-0 dashboard-card-title">Disponibilidade</h3>
          </div>
          <div className="zen-card-body">
            <AnalyticsHeatmap />
          </div>
        </div>
      </div>
      <div className="zen-card">
        <div className="zen-card-header">
          <h3 className="mb-0 dashboard-card-title">A escola em números</h3>
        </div>
        <div className="zen-card-body">
          <ResourceCounts resources={data?.resources} isLoading={isLoading} />
        </div>
      </div>
    </div>
  )
}
