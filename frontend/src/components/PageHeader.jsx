const PageHeader = ({ preTitle, title, description, context, actions, children }) => {
  const headerActions = actions ?? children

  return (
    <header className="page-header">
      <div className="page-header__copy">
        {preTitle && <span className="page-header__pretitle">{preTitle}</span>}
        <h1 className="page-header__title">{title}</h1>
        {context && <p className="page-header__context">{context}</p>}
        {description && <p className="page-header__description">{description}</p>}
      </div>
      {headerActions && (
        <div className="page-header__actions">
          <span className="page-header__rule" aria-hidden="true" />
          {headerActions}
        </div>
      )}
    </header>
  )
}

export default PageHeader
