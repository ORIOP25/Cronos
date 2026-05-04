import React from 'react'
import './Skeleton.css'

/**
 * SkeletonGrid — placeholder animado para grelhas (WeekGrid, AvailabilityGrid).
 * Mostra uma grelha de células com shimmer.
 */
const SkeletonGrid = ({ rows = 6, cols = 5 }) => {
  return (
    <div style={{ padding: '8px' }}>
      {/* Header row */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: `96px repeat(${cols}, 1fr)`,
        gap: '4px',
        marginBottom: '8px',
      }}>
        <div
          className="skeleton-shimmer"
          style={{ height: '28px', borderRadius: '4px' }}
        />
        {Array.from({ length: cols }).map((_, i) => (
          <div
            key={`gh-${i}`}
            className="skeleton-shimmer"
            style={{ height: '28px', borderRadius: '4px' }}
          />
        ))}
      </div>

      {/* Data rows */}
      {Array.from({ length: rows }).map((_, rowIdx) => (
        <div
          key={`gr-${rowIdx}`}
          style={{
            display: 'grid',
            gridTemplateColumns: `96px repeat(${cols}, 1fr)`,
            gap: '4px',
            marginBottom: '4px',
          }}
        >
          <div
            className="skeleton-shimmer"
            style={{ height: '60px', borderRadius: '4px' }}
          />
          {Array.from({ length: cols }).map((_, colIdx) => (
            <div
              key={`gc-${rowIdx}-${colIdx}`}
              className="skeleton-shimmer"
              style={{ height: '60px', borderRadius: '4px' }}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

export default SkeletonGrid
