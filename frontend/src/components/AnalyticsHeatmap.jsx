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

  // Cores mais suaves e modernas (Estilo GitHub)
  const getSlotStyle = (stats) => {
    if (!stats) return { bg: '#ebedf0', border: '#e1e4e8' } // Cinza claro
    const r = stats.availability_ratio
    
    // Gradiente de Verde (Saudável) a Vermelho (Crítico)
    if (r < 0.3) return { bg: '#ffebe9', border: '#ff8182', text: '#cf222e' } // Vermelho Suave
    if (r < 0.6) return { bg: '#fff8c5', border: '#d4a72c', text: '#9a6700' } // Amarelo Suave
    return { bg: '#dafbe1', border: '#4ac26b', text: '#1a7f37' } // Verde Suave
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
    <div className="mb-2">
      <div className="d-flex justify-content-between align-items-end mb-3">
        <div>
          <h6 className="m-0 fw-bold text-dark">Raio-X de Disponibilidade</h6>
          <small className="text-muted">Capacidade da escola para alocar aulas</small>
        </div>
        <div className="d-flex gap-2 small">
          <span className="d-flex align-items-center gap-1"><div style={{width: 8, height: 8, background: '#4ac26b', borderRadius: '50%'}}></div> Bom</span>
          <span className="d-flex align-items-center gap-1"><div style={{width: 8, height: 8, background: '#d4a72c', borderRadius: '50%'}}></div> Médio</span>
          <span className="d-flex align-items-center gap-1"><div style={{width: 8, height: 8, background: '#ff8182', borderRadius: '50%'}}></div> Crítico</span>
        </div>
      </div>

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