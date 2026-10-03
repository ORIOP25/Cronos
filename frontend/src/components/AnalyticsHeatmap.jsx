import { CTooltip } from '@coreui/react'
import { useTimeslots } from '../features/catalog/data'
import { useAvailabilityHeatmap } from '../features/schoolConfig/data'
import StatePanel from './StatePanel'

const DAYS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']

function getHeatmapStyle(stats) {
  if (!stats) return { backgroundColor: 'var(--rs-heat-neutral-bg)', borderColor: 'var(--rs-heat-neutral-border)' }
  if (stats.availability_ratio < 0.3) return { backgroundColor: 'var(--rs-heat-critical-bg)', borderColor: 'var(--rs-heat-critical-border)', color: 'var(--rs-heat-critical-text)' }
  if (stats.availability_ratio < 0.6) return { backgroundColor: 'var(--rs-heat-medium-bg)', borderColor: 'var(--rs-heat-medium-border)', color: 'var(--rs-heat-medium-text)' }
  return { backgroundColor: 'var(--rs-heat-good-bg)', borderColor: 'var(--rs-heat-good-border)', color: 'var(--rs-heat-good-text)' }
}

export default function AnalyticsHeatmap() {
  const timeslotsQuery = useTimeslots()
  const heatmapQuery = useAvailabilityHeatmap()
  if (timeslotsQuery.isLoading || heatmapQuery.isLoading) return <StatePanel state="loading" title="A carregar disponibilidade" compact />
  if (timeslotsQuery.isError || heatmapQuery.isError) return <StatePanel state="error" title="Não foi possível carregar a disponibilidade" description="Tente novamente quando a ligação estiver disponível." action={<button type="button" className="btn btn-link" onClick={() => { void timeslotsQuery.refetch(); void heatmapQuery.refetch() }}>Tentar novamente</button>} compact />
  const timeslots = timeslotsQuery.data ?? []
  const heatmapData = heatmapQuery.data ?? []
  if (!timeslots.length) return <StatePanel state="empty" title="Sem blocos configurados" description="A disponibilidade aparece depois de configurar a grelha horária." compact />
  const slotsByDay = timeslots.reduce((acc, slot) => { (acc[slot.day_of_week] ??= []).push(slot); return acc }, {})
  Object.values(slotsByDay).forEach((slots) => slots.sort((a, b) => a.start_time.localeCompare(b.start_time)))
  const summary = heatmapData.length ? `A grelha mostra a disponibilidade de professores em ${heatmapData.length} blocos.` : 'Ainda não existem dados de disponibilidade para estes blocos.'
  return <div className="availability-heatmap">
    <p className="text-muted small mb-3">{summary}</p>
    <div className="availability-heatmap__legend" aria-label="Legenda da disponibilidade"><span><i className="is-good" /> Boa</span><span><i className="is-medium" /> Intermédia</span><span><i className="is-critical" /> Crítica</span></div>
    <p className="availability-heatmap__hint d-lg-none small text-muted mb-1">Deslize horizontalmente para ver todos os dias.</p>
    <div className="availability-heatmap__days" role="region" aria-label="Disponibilidade por dia" tabIndex={0}>
      {Object.entries(slotsByDay).sort(([a], [b]) => Number(a) - Number(b)).map(([day, slots]) => <div className="availability-heatmap__day" key={day}><div className="availability-heatmap__day-label">{DAYS[day] ?? `Dia ${Number(day) + 1}`}</div>{slots.map((slot) => { const stats = heatmapData.find((item) => item.timeslot_id === slot.id); const available = stats?.available_count ?? '-'; const total = stats?.total_teachers ?? '-'; return <CTooltip content={`Disponíveis: ${available} / ${total}`} key={slot.id}><div className="availability-heatmap__slot" style={getHeatmapStyle(stats)} aria-label={`${DAYS[day] ?? `Dia ${Number(day) + 1}`} às ${slot.start_time.slice(0, 5)}: ${available} de ${total} professores disponíveis`}><strong>{slot.start_time.slice(0, 5)}</strong><span>{available}/{total}</span></div></CTooltip> })}</div>)}
    </div>
  </div>
}
