export default function StatePanel({ state, title, description, action, compact = false, children }) {
  if (!['loading', 'error', 'empty'].includes(state)) return null
  return (
    <section className={`state-panel state-panel--${state}${compact ? ' state-panel--compact' : ''}`} aria-busy={state === 'loading' ? 'true' : undefined}>
      {state === 'loading' && <span className="state-panel__spinner" aria-hidden="true" />}
      {children}
      <h2 className="state-panel__title">{title}</h2>
      {description && <p className="state-panel__description">{description}</p>}
      {action && <div className="state-panel__action">{action}</div>}
    </section>
  )
}
