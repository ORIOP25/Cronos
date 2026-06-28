import React from 'react'
import PropTypes from 'prop-types'

const PageHeader = ({ preTitle, title, children }) => {
  return (
    <div className="d-flex justify-content-between align-items-end mb-5 flex-wrap gap-3">
      <div>
        {preTitle && (
          <span className="zen-caps" style={{ color: 'var(--brand-600)' }}>
            {preTitle}
          </span>
        )}
        <h1 className="text-display mt-2" style={{ fontSize: '3rem', color: 'var(--brand-950)' }}>
          <span className="text-editorial">{title}</span>
        </h1>
      </div>
      <div className="d-flex align-items-end gap-3 flex-wrap">
        <div className="luxury-line" style={{ width: '100px', marginBottom: '14px' }} />
        {children}
      </div>
    </div>
  )
}

PageHeader.propTypes = {
  preTitle: PropTypes.string,
  title: PropTypes.string.isRequired,
  children: PropTypes.node,
}

export default PageHeader
