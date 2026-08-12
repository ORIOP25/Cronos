import { Show } from '@clerk/react'
import { Outlet } from 'react-router-dom'
import { SignedInRedirect } from '../../../../routeGuards'
import MarketingHeader from './MarketingHeader'
import MarketingFooter from './MarketingFooter'
import ScrollToTopButton from '../shared/ScrollToTopButton'
import { useScrollToTop } from '../../hooks/useScrollToTop'
import { useMarketingMetadata } from '../../hooks/useMarketingMetadata'
import '../../../../pages/MarketingSite.css'

export default function MarketingLayout() {
  useScrollToTop()
  useMarketingMetadata()

  return (
    <Show when="signed-out" fallback={<SignedInRedirect />}>
      <div className="cronos-marketing">
        <MarketingHeader />
        <main><Outlet /></main>
        <MarketingFooter />
        <ScrollToTopButton />
      </div>
    </Show>
  )
}
