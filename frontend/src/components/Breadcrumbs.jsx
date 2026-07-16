import { Link } from 'react-router-dom'
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
    <nav aria-label="Navegação estrutural" className="mb-4">
      <ol className="breadcrumb mb-0 flex-wrap small">
        {items.map((item, idx) => {
          const isLast = idx === items.length - 1
          return (
            <li key={item.label} className={`breadcrumb-item${isLast ? ' active' : ''}`} aria-current={isLast ? 'page' : undefined}>
              {isLast ? (
                item.label
              ) : (
                <Link to={item.to}>{item.label}</Link>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

export default Breadcrumbs
