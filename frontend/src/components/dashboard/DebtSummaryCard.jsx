import { useNavigate } from 'react-router-dom'

export default function DebtSummaryCard({ debts, isLoading }) {
  const navigate = useNavigate()
  const hasDebt = (debts?.total_hours_owed ?? 0) > 0
  return (
    <div data-testid="debt-summary" className="zen-card dashboard-debt-card">
      <div className="zen-card-header"><h3 className="mb-0 dashboard-card-title">Dívidas de Horas</h3></div>
      <div className="zen-card-body text-center py-3 dashboard-debt-card__body">
        {isLoading ? (
          <div className="dashboard-metric-skeleton mx-auto" />
        ) : (
          <>
            <div className="d-flex justify-content-center gap-4 mb-3">
              <div><span className="text-display d-block dashboard-debt-value" data-alert={hasDebt}>{debts?.total_hours_owed ?? 0}h</span><small>horas em dívida</small></div>
              <div><span className="text-display d-block dashboard-debt-value">{debts?.total_gaps ?? 0}</span><small>gaps</small></div>
            </div>
            <div className="small text-muted mb-2">
              {debts?.affected_classes_count ?? 0} turmas afetadas
              {(debts?.total_hours_owed_overdue ?? 0) > 0 && <> · {debts.total_hours_owed_overdue}h vencidas</>}
            </div>
            <button type="button" className="btn btn-link btn-sm" onClick={() => navigate('/absences?view=debts')}>Ver detalhes →</button>
          </>
        )}
      </div>
    </div>
  )
}
