import PropTypes from 'prop-types'
import { getSubjectColor } from '../../utils/subjectColors'

const KPISidebar = ({ subjects }) => {
  if (!subjects || subjects.length === 0) {
    return (
      <div className="text-muted text-center p-3" style={{ fontSize: '0.85rem' }}>
        Nenhuma disciplina com progresso disponível.
      </div>
    )
  }

  return (
    <div className="d-flex flex-column gap-3">
      {subjects.map(subj => {
        const pct   = subj.overall_percentage ?? 0
        const color = getSubjectColor(subj.id)
        return (
          <div key={subj.id}>
            <div className="d-flex justify-content-between align-items-center mb-1">
              <div
                className="fw-semibold text-truncate me-2"
                style={{ fontSize: '0.8rem', borderLeft: `3px solid ${color}`, paddingLeft: '6px' }}
              >
                {subj.name}
              </div>
              <span className="text-muted" style={{ fontSize: '0.75rem', whiteSpace: 'nowrap' }}>
                {subj.completed_hours}h / {subj.total_hours}h
              </span>
            </div>
            <progress
              value={pct}
              max={100}
              style={{ width: '100%', height: '6px', accentColor: color, borderRadius: '3px' }}
              aria-label={`${subj.name}: ${pct.toFixed(1)}%`}
            />
            <div className="text-end text-muted" style={{ fontSize: '0.7rem', marginTop: '2px' }}>
              {pct.toFixed(1)}%
            </div>
          </div>
        )
      })}
    </div>
  )
}

KPISidebar.propTypes = {
  subjects: PropTypes.arrayOf(
    PropTypes.shape({
      id:                 PropTypes.number.isRequired,
      name:               PropTypes.string.isRequired,
      completed_hours:    PropTypes.number,
      total_hours:        PropTypes.number,
      overall_percentage: PropTypes.number,
    }),
  ),
}

export default KPISidebar
