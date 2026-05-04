import React from 'react'
import { useQuery } from '@tanstack/react-query'
import apiClient from '../apiClient'
import { CSpinner, CTooltip } from '@coreui/react'

const daysOfWeek = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"] // Nomes curtos

const AnalyticsHeatmap = () => {
  const { data: timeslots } = useQuery({
    queryKey: ['timeslots'],
    queryFn: async () => (await apiClient.get('/import/timeslots')).data
  })

  const { data: heatmapData, isLoading } = useQuery({
    queryKey: ['heatmap'],
    queryFn: async () => (await apiClient.get('/analytics/availability-heatmap')).data
  })

  // Cores quentes alinhadas com Retro Sunset
  const getSlotStyle = (stats) => {
    if (!stats) return { bg: 'var(--rs-heat-neutral-bg)', border: 'var(--rs-heat-neutral-border)' }
    const r = stats.availability_ratio
    
    if (r < 0.3) return { bg: 'var(--rs-heat-critical-bg)', border: 'var(--rs-heat-critical-border)', text: 'var(--rs-heat-critical-text)' }
    if (r < 0.6) return { bg: 'var(--rs-heat-medium-bg)', border: 'var(--rs-heat-medium-border)', text: 'var(--rs-heat-medium-text)' }
    return { bg: 'var(--rs-heat-good-bg)', border: 'var(--rs-heat-good-border)', text: 'var(--rs-heat-good-text)' }
  }

  if (isLoading) return <div className="text-center p-3 text-muted small"><CSpinner size="sm"/> A carregar dados...</div>

  // Organizar dados
  const slotsByDay = (timeslots || []).reduce((acc, slot) => {
    if (!acc[slot.day_of_week]) acc[slot.day_of_week] = []
    acc[slot.day_of_week].push(slot)
    return acc
  }, {})
  
  Object.keys(slotsByDay).forEach(day => {
    slotsByDay[day].sort((a, b) => a.start_time.localeCompare(b.start_time))
  })

  return (
    <div>
      <div className="d-flex gap-2 overflow-auto pb-2">
        {[0, 1, 2, 3, 4, 5].map(dayIndex => {
          const daySlots = slotsByDay[dayIndex]
          if (!daySlots || daySlots.length === 0) return null

          return (
            <div key={dayIndex} className="flex-grow-1" style={{ minWidth: '100px' }}>
              <div className="text-uppercase text-muted fw-bold mb-2" style={{fontSize: '0.7rem', letterSpacing: '1px'}}>
                {daysOfWeek[dayIndex]}
              </div>
              <div className="d-flex flex-column gap-1">
                {daySlots.map(slot => {
                  const stats = heatmapData?.find(h => h.timeslot_id === slot.id)
                  const style = getSlotStyle(stats)
                  const avail = stats ? stats.available_count : '-'
                  const total = stats ? stats.total_teachers : '-'

                  return (
                    <CTooltip content={`Disponíveis: ${avail} / ${total}`} key={slot.id}>
                      <div 
                        className="rounded p-2 d-flex justify-content-between align-items-center"
                        style={{
                          backgroundColor: style.bg,
                          border: `1px solid ${style.border}`,
                          color: style.text,
                          cursor: 'help',
                          fontSize: '0.75rem'
                        }}
                      >
                        <span className="fw-semibold">{slot.start_time.slice(0, 5)}</span>
                        <span className="opacity-75">{avail}/{total}</span>
                      </div>
                    </CTooltip>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default AnalyticsHeatmap