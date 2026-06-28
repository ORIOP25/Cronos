import React from 'react'
import PropTypes from 'prop-types'
import { CBadge } from '@coreui/react'

const STATUS_LABELS = {
  OPEN: 'Aberta',
  SUBMITTED: 'Submetida',
  APPROVED: 'Aprovada',
}

const STATUS_COLORS = {
  OPEN: 'secondary',
  SUBMITTED: 'info',
  APPROVED: 'success',
}

const STATUS_BG_COLORS = {
  OPEN: '#f8f9fa',
  SUBMITTED: '#fff3cd',
  APPROVED: '#d1e7dd',
}

const TeacherCard = ({ teacher, isSelected, onClick }) => {
  const color = STATUS_COLORS[teacher.status] || 'secondary'
  const bg = isSelected ? (STATUS_BG_COLORS[teacher.status] || '#e7f1ff') : '#fff'
  const registered = teacher.registered_slots ?? 0
  const total = teacher.total_slots ?? 0

  return (
    <button
      type="button"
      onClick={onClick}
      className="w-100 text-start border-0 mb-2 p-3 rounded"
      style={{
        backgroundColor: bg,
        borderLeft: `4px solid var(--cui-${color})`,
        cursor: 'pointer',
        transition: 'all 0.15s ease',
        boxShadow: isSelected ? '0 0 0 2px var(--cui-primary)' : '0 1px 3px rgba(0,0,0,0.08)',
      }}
    >
      <div className="d-flex justify-content-between align-items-center mb-1">
        <span className="fw-semibold" style={{ fontSize: '0.9rem' }}>
          {teacher.teacher_name || `Prof. #${teacher.teacher_id}`}
        </span>
        <CBadge color={color} style={{ fontSize: '0.7rem' }}>
          {STATUS_LABELS[teacher.status] || teacher.status}
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

TeacherCard.propTypes = {
  teacher: PropTypes.shape({
    teacher_id: PropTypes.number.isRequired,
    teacher_name: PropTypes.string,
    status: PropTypes.string,
    registered_slots: PropTypes.number,
    total_slots: PropTypes.number,
    completed_slots: PropTypes.number,
    occurrence_slots: PropTypes.number,
  }).isRequired,
  isSelected: PropTypes.bool,
  onClick: PropTypes.func.isRequired,
}

TeacherCard.defaultProps = {
  isSelected: false,
}

export default TeacherCard
