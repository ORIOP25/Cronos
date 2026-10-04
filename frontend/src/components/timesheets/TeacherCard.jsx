import { CBadge } from '@coreui/react'
import { getTimesheetStatus } from '../../utils/presentation'

const TeacherCard = ({ teacher, isSelected, onClick }) => {
  const status = getTimesheetStatus(teacher.status)
  const bg = isSelected ? status.background : '#fff'
  const registered = teacher.registered_slots ?? 0
  const total = teacher.total_slots ?? 0

  return (
    <button
      type="button"
      onClick={onClick}
      className="w-100 text-start border-0 mb-2 p-3 rounded"
      style={{
        backgroundColor: bg,
        borderLeft: `4px solid var(--cui-${status.color})`,
        cursor: 'pointer',
        transition: 'all 0.15s ease',
        boxShadow: isSelected ? '0 0 0 2px var(--cui-primary)' : '0 1px 3px rgba(0,0,0,0.08)',
      }}
    >
      <div className="d-flex justify-content-between align-items-center mb-1">
        <span className="fw-semibold" style={{ fontSize: '0.9rem' }}>
          {teacher.teacher_name || 'Professor por identificar'}
        </span>
        <CBadge color={status.color} style={{ fontSize: '0.7rem' }}>
          {status.label}
        </CBadge>
      </div>
      <div className="text-muted" style={{ fontSize: '0.78rem' }}>
        {total > 0 ? (
          <strong>{registered}</strong>
        ) : (
          <span>—</span>
        )}/{total} registadas
      </div>
    </button>
  )
}

TeacherCard.defaultProps = {
  isSelected: false,
}

export default TeacherCard
