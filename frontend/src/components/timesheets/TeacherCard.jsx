import { CBadge } from '@coreui/react'
import { getTimesheetStatus } from '../../utils/presentation'
import { formatWeekRange } from '../../utils/formatUtils'

const TeacherCard = ({ teacher, isSelected = false, onClick, showWeek = false }) => {
  const status = getTimesheetStatus(teacher.status)
  const registered = teacher.registered_slots ?? 0
  const total = teacher.total_slots ?? 0

  return (
    <button
      type="button"
      onClick={onClick}
      className="teacher-list-row"
      aria-pressed={isSelected}
    >
      <div className="d-flex justify-content-between align-items-center mb-1">
        <span className="fw-semibold" style={{ fontSize: '0.9rem' }}>
          {teacher.teacher_name || 'Professor por identificar'}
        </span>
        <CBadge color={status.color} style={{ fontSize: '0.7rem' }}>
          {status.label}
        </CBadge>
      </div>
      {showWeek && <div className="small text-muted">{formatWeekRange(teacher.week_start_date)}</div>}
      {!showWeek && <div className="text-muted" style={{ fontSize: '0.78rem' }}>
        {total > 0 ? (
          <strong>{registered}</strong>
        ) : (
          <span>—</span>
        )}/{total} registadas
      </div>}
    </button>
  )
}

export default TeacherCard
