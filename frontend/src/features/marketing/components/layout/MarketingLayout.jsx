import { Show, useAuth } from '@clerk/react'
import { Outlet } from 'react-router-dom'
import { SignedInRedirect } from '../../../../routeGuards'
import MarketingHeader from './MarketingHeader'
import MarketingFooter from './MarketingFooter'
import ScrollToTopButton from '../shared/ScrollToTopButton'
import { useScrollToTop } from '../../hooks/useScrollToTop'
import { useMarketingMetadata } from '../../hooks/useMarketingMetadata'
import '../../../../pages/MarketingSite.css'

export default function MarketingLayout({ allowSignedIn = false }) {
  const { isLoaded, isSignedIn } = useAuth({ treatPendingAsSignedOut: false })
  useScrollToTop()
  useMarketingMetadata(allowSignedIn || !isLoaded || !isSignedIn)

  const content = (
    <div className="cronos-marketing">
      <MarketingHeader />
      <main><Outlet /></main>
      <MarketingFooter />
      <ScrollToTopButton />
    </div>
  )

  if (allowSignedIn) return content

  return (
    <Show when="signed-out" treatPendingAsSignedOut={false} fallback={<SignedInRedirect />}>
      {content}
    </Show>
  )
}
