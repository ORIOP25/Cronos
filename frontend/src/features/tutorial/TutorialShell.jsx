import DefaultLayout from '../../components/DefaultLayout'

export function TutorialShell({ activeNavItem, children, panel }) {
  return (
    <DefaultLayout activePath={activeNavItem} navigationDisabled navigationRole="admin" className="tutorial-live-shell">
      <div data-testid="tutorial-workspace">
        <div className="tutorial-demo-ribbon" role="status">Ambiente de demonstração · nenhum dado real será alterado</div>
        {children}
        {panel}
      </div>
    </DefaultLayout>
  )
}
