const PageHeader = ({ title, description, context, actions, children }) => {
  const headerActions = actions ?? children

  return (
    <header className="page-header">
      <div className="page-header__copy">
        <h1 className="page-header__title">{title}</h1>
        {context && <p className="page-header__context">{context}</p>}
        {description && <p className="page-header__description">{description}</p>}
      </div>
      {headerActions && (
        <div className="page-header__actions" role="group" aria-label="Ações da página">
          {headerActions}
        </div>
      )}
    </header>
  )
}

export default PageHeader
