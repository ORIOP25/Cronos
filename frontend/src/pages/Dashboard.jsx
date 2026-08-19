import AnalyticsHeatmap from '../components/AnalyticsHeatmap'
import AlertBar from '../components/dashboard/AlertBar'
import ResourceCounts from '../components/dashboard/ResourceCounts'
import ScheduleHealthCard from '../components/dashboard/ScheduleHealthCard'
import ClassProgressOverview from '../components/dashboard/ClassProgressOverview'
import DebtSummaryCard from '../components/dashboard/DebtSummaryCard'
import { useDashboard } from '../features/operations/data'
import PageHeader from '../components/PageHeader'
import StatePanel from '../components/StatePanel'
import { getApiErrorMessage } from '../utils/apiErrors'

export default function Dashboard() {
  const { data, isLoading, isError, error } = useDashboard()
  const currentDate = new Intl.DateTimeFormat('pt-PT', { dateStyle: 'long' }).format(new Date())
  const header = <PageHeader preTitle="Visão Geral" title="Painel de Controlo" context={data?.organization_name ? `Organização: ${data.organization_name}` : undefined} description={`Hoje, ${currentDate}.`} />
  if (isError) return <div>{header}<StatePanel state="error" title="Não foi possível carregar o dashboard" description={getApiErrorMessage(error, 'Tente novamente mais tarde.')} /></div>
  return <div>
    {header}
    <div className="mb-4"><AlertBar alerts={data?.alerts} isLoading={isLoading} /></div>
    <div className="mb-4"><ScheduleHealthCard health={data?.schedule_health} isLoading={isLoading} /></div>
    <div className="mb-4"><ClassProgressOverview progress={data?.class_progress} isLoading={isLoading} /></div>
    <div className="dashboard-secondary-grid mb-4">
      <DebtSummaryCard debts={data?.debts} isLoading={isLoading} />
      <div className="zen-card"><div className="zen-card-header"><h3 className="mb-0 dashboard-card-title">Disponibilidade</h3></div><div className="zen-card-body"><AnalyticsHeatmap /></div></div>
    </div>
    <div className="zen-card"><div className="zen-card-header"><h3 className="mb-0 dashboard-card-title">Recursos</h3></div><div className="zen-card-body"><ResourceCounts resources={data?.resources} isLoading={isLoading} /></div></div>
  </div>
}
