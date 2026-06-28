import React from 'react'
import './Skeleton.css'

/**
 * SkeletonTable — placeholder animado para estados de carregamento de tabelas.
 * Mostra N linhas com barras shimmer que simulam a estrutura da tabela.
 */
const SkeletonTable = ({ rows = 5, columns = 3 }) => {
  return (
    <div style={{ padding: '0' }}>
      {/* Header */}
      <div className="skeleton-header" style={{
        display: 'flex',
        gap: '20px',
        padding: '16px 20px',
        borderBottom: '1px solid var(--color-border-default)',
      }}>
        {Array.from({ length: columns }).map((_, i) => (
          <div
            key={`h-${i}`}
            className="skeleton-shimmer"
            style={{
              height: '12px',
              width: `${Math.max(30, 100 - i * 15)}%`,
              borderRadius: '4px',
            }}
          />
        ))}
      </div>

      {/* Rows */}
      {Array.from({ length: rows }).map((_, rowIdx) => (
        <div
          key={`r-${rowIdx}`}
          style={{
            display: 'flex',
            gap: '20px',
            padding: '18px 20px',
            borderBottom: '1px solid var(--zen-table-border)',
          }}
        >
          {Array.from({ length: columns }).map((_, colIdx) => (
            <div
              key={`c-${rowIdx}-${colIdx}`}
              className="skeleton-shimmer"
              style={{
                height: '14px',
                width: `${Math.max(20, 80 - colIdx * 10 - rowIdx * 5)}%`,
                borderRadius: '4px',
              }}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

export default SkeletonTable
