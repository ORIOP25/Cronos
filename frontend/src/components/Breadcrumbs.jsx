import React from 'react'
import { Link } from 'react-router-dom'
import PropTypes from 'prop-types'

/**
 * Breadcrumbs — navegação hierárquica para páginas de cursos.
 *
 * Uso:
 *   <Breadcrumbs items={[
 *     { label: 'Cursos', to: '/courses' },
 *     { label: 'TGPSI 2025', to: '/courses/1' },
 *     { label: '10º TGPSI' },
 *   ]} />
 *
 * O último item (sem `to`) é renderizado como texto ativo (não link).
 */
const Breadcrumbs = ({ items = [] }) => {
  if (!items.length) return null

  return (
    <nav aria-label="Navegação estrutural" style={{ marginBottom: '20px' }}>
      <ol style={{
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        listStyle: 'none',
        padding: 0,
        margin: 0,
        fontSize: '0.82rem',
        fontFamily: 'var(--font-body)',
        flexWrap: 'wrap',
      }}>
        {items.map((item, idx) => {
          const isLast = idx === items.length - 1
          return (
            <li key={item.label} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              {isLast ? (
                <span style={{ color: 'var(--brand-950)', fontWeight: 600 }}>
                  {item.label}
                </span>
              ) : (
                <>
                  <Link
                    to={item.to}
                    style={{
                      color: 'var(--brand-600)',
                      textDecoration: 'none',
                      transition: 'color 0.2s ease',
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--brand-800)' }}
                    onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--brand-600)' }}
                  >
                    {item.label}
                  </Link>
                  <span style={{ color: 'var(--brand-500)', userSelect: 'none' }}>›</span>
                </>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

Breadcrumbs.propTypes = {
  items: PropTypes.arrayOf(
    PropTypes.shape({
      label: PropTypes.string.isRequired,
      to: PropTypes.string,
    })
  ),
}

export default Breadcrumbs
