import React from 'react'
import PropTypes from 'prop-types'

const FormattedList = ({ items, limit = 3 }) => {
  if (!items || !items.length) {
    return <span className="text-muted">-</span>
  }
  
  if (items.length > limit) {
    const visible = items.slice(0, limit)
    const hiddenCount = items.length - limit
    return (
      <span title={items.join(', ')}>
        {visible.join(', ')} (+{hiddenCount})
      </span>
    )
  }
  
  return <span>{items.join(', ')}</span>
}

FormattedList.propTypes = {
  items: PropTypes.arrayOf(PropTypes.string),
  limit: PropTypes.number
}

export default FormattedList
