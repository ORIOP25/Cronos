import React from 'react'
import { useNavigate } from 'react-router-dom'
import { CCol, CRow } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilWarning, cilCheckCircle, cilClock, cilSwapHorizontal } from '@coreui/icons'

const alertCards = [
  {
    key: 'ocorrencias',
    label: 'Ocorrências hoje',
    icon: cilWarning,
    route: '/absences?date=today&status=PENDING',
  },
  {
    key: 'timesheets',
    label: 'Timesheets',
    icon: cilClock,
    route: '/timesheets?status=submitted',
  },
  {
    key: 'drafts',
    label: 'Rascunhos',
    icon: cilCheckCircle,
    route: '/schedules?tab=drafts',
  },
  {
    key: 'substituicoes',
    label: 'Substituições hoje',
    icon: cilSwapHorizontal,
    route: '/absences?view=substitutions&date=today',
  },
]

function getColor(value) {
  if (value === 0) return 'var(--rs-teal)'
  if (value <= 4) return 'var(--brand-500)'
  return 'var(--rs-deep)'
}

function SkeletonCard() {
  return (
    <CCol xs={6} md={3} className="mb-3">
      <div
        style={{
          background: 'var(--color-bg-surface)',
          border: '1px solid var(--color-border-default)',
          borderRadius: 10,
          padding: '18px 16px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 8,
          minHeight: 90,
        }}
      >
        <div
          style={{
            width: 42,
            height: 42,
            borderRadius: '50%',
            background: 'var(--color-bg-surface-strong)',
          }}
        />
        <div
          style={{
            width: 32,
            height: 18,
            borderRadius: 4,
            background: 'var(--color-bg-surface-strong)',
          }}
        />
      </div>
    </CCol>
  )
}

export default function AlertBar({ alerts, isLoading }) {
  const navigate = useNavigate()

  if (isLoading) {
    return (
      <div data-testid="alert-bar">
        <CRow>
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </CRow>
      </div>
    )
  }

  return (
    <div data-testid="alert-bar">
      <CRow>
        {alertCards.map((card) => {
          const value = alerts?.[`pending_${card.key === 'ocorrencias' ? 'occurrences_today' : card.key === 'substituicoes' ? 'active_substitutions_today' : `pending_${card.key}`}`] ?? 0
          const color = getColor(value)
          return (
            <CCol key={card.key} xs={6} md={3} className="mb-3">
              <button
                data-testid={`alert-${card.key}`}
                onClick={() => navigate(card.route)}
                className="zen-alert-card"
                style={{
                  width: '100%',
                  padding: '18px 16px',
                  border: '1px solid var(--color-border-default)',
                  borderRadius: 10,
                  background: 'var(--color-bg-surface)',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: 8,
                  transition: 'transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease',
                  '--hover-color': color,
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'translateY(-2px)'
                  e.currentTarget.style.boxShadow = '0 6px 24px var(--color-shadow-strong)'
                  e.currentTarget.style.borderColor = color
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = ''
                  e.currentTarget.style.boxShadow = ''
                  e.currentTarget.style.borderColor = 'var(--color-border-default)'
                }}
              >
                <CIcon
                  icon={card.icon}
                  style={{ width: 22, height: 22, color }}
                />
                <span
                  className="text-display"
                  style={{
                    fontSize: '2rem',
                    fontWeight: 700,
                    color,
                    lineHeight: 1,
                    transition: 'color 0.3s ease',
                  }}
                >
                  {value}
                </span>
                <span
                  style={{
                    fontSize: '0.75rem',
                    color: 'var(--rs-muted)',
                    fontWeight: 500,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}
                >
                  {card.label}
                </span>
              </button>
            </CCol>
          )
        })}
      </CRow>
    </div>
  )
}
