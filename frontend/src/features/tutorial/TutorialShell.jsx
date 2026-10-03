import { useEffect } from 'react'
import { toast } from 'react-hot-toast'
import DefaultLayout from '../../components/DefaultLayout'
import { TUTORIAL_COPY } from './tutorialContent'

export function TutorialShell({ activeNavItem, children, panel }) {
  useEffect(() => () => { toast.removeAll() }, [])

  return (
    <DefaultLayout activePath={activeNavItem} navigationDisabled navigationRole="admin" className="tutorial-live-shell">
      <div data-testid="tutorial-workspace">
        <div className="tutorial-demo-ribbon" role="status">{TUTORIAL_COPY.ribbon}</div>
        {children}
        {panel}
      </div>
    </DefaultLayout>
  )
}
