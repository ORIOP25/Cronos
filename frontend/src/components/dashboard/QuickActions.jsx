import { useNavigate } from 'react-router-dom'
import { CButton } from '@coreui/react'

const ACTIONS = [
  {
    key: 'timesheets',
    label: 'Aprovar timesheets',
    route: '/timesheets?status=submitted',
    condition: (alerts) => (alerts?.pending_timesheets ?? 0) > 0,
    count: (alerts) => alerts?.pending_timesheets ?? 0,
  },
  {
    key: 'drafts',
    label: 'Rever rascunho pendente',
    route: '/schedules?tab=drafts',
    condition: (alerts) => (alerts?.pending_drafts ?? 0) > 0,
    count: (alerts) => alerts?.pending_drafts ?? 0,
  },
]

export default function QuickActions({ alerts }) {
  const navigate = useNavigate()

  const visible = ACTIONS.filter((a) => a.condition(alerts))

  if (visible.length === 0) return null

  return (
    <div className="d-flex flex-wrap gap-2">
      {visible.map((action) => {
        const count = action.count?.(alerts)
        return (
          <CButton
            key={action.key}
            data-testid={`action-${action.key}`}
            color="primary"
            variant="outline"
            size="sm"
            style={{
              borderColor: 'var(--brand-600)',
              color: 'var(--brand-800)',
              fontWeight: 500,
              fontSize: '0.8rem',
            }}
            onClick={() => navigate(action.route)}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'var(--brand-100)'
              e.currentTarget.style.borderColor = 'var(--brand-500)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = ''
              e.currentTarget.style.borderColor = 'var(--brand-600)'
            }}
          >
            {action.label}
            {count !== null && count > 0 && (
              <span
                style={{
                  marginLeft: 6,
                  background: 'var(--brand-500)',
                  color: '#fff',
                  borderRadius: 10,
                  padding: '1px 8px',
                  fontSize: '0.7rem',
                  fontWeight: 600,
                }}
              >
                {count}
              </span>
            )}
          </CButton>
        )
      })}
    </div>
  )
}
