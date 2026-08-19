export default function GuidedFormShell({ eyebrow, title, summary, meta, visual, children }) {
  return (
    <main className="guided-form-shell">
      <div className="guided-form-shell__intro">
        <p className="guided-form-shell__eyebrow">{eyebrow}</p>
        <h1 className="guided-form-shell__title">{title}</h1>
        {summary && <p className="guided-form-shell__summary">{summary}</p>}
        {meta && <p className="guided-form-shell__meta">{meta}</p>}
        {visual ?? <div className="guided-form-shell__visual" aria-hidden="true" />}
      </div>
      <section className="guided-form-shell__card" aria-label={typeof title === 'string' ? title : undefined}>{children}</section>
    </main>
  )
}
