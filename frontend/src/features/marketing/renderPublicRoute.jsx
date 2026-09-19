import { renderToStaticMarkup } from 'react-dom/server'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import MarketingHeader from './components/layout/MarketingHeader'
import MarketingFooter from './components/layout/MarketingFooter'
import ScrollToTopButton from './components/shared/ScrollToTopButton'
import HomePage from '../../pages/marketing/HomePage'
import VantagensPage from '../../pages/marketing/VantagensPage'
import HowItWorksPage from '../../pages/marketing/HowItWorksPage'
import AboutPage from '../../pages/marketing/AboutPage'
import HelpPage from '../../pages/marketing/HelpPage'
import ContactPage from '../../pages/marketing/ContactPage'
import LegalDocumentLayout from '../legal/LegalDocumentLayout'
import { StaticNotFoundPage } from '../../pages/NotFoundPage'

const routeDefinitions = new Map([
  ['/', { route: '/', page: <HomePage /> }],
  ['/vantagens', { route: '/vantagens', page: <VantagensPage /> }],
  ['/como-funciona', { route: '/como-funciona', page: <HowItWorksPage /> }],
  ['/sobre', { route: '/sobre', page: <AboutPage /> }],
  ['/about', { route: '/sobre', page: <AboutPage /> }],
  ['/ajuda', { route: '/ajuda', page: <HelpPage /> }],
  ['/contacto', { route: '/contacto', page: <ContactPage /> }],
  ['/contact', { route: '/contacto', page: <ContactPage /> }],
  ['/privacidade', { route: '/privacidade', page: <LegalDocumentLayout kind="privacy" /> }],
  ['/privacy', { route: '/privacidade', page: <LegalDocumentLayout kind="privacy" /> }],
  ['/termos', { route: '/termos', page: <LegalDocumentLayout kind="terms" /> }],
  ['/dpa', { route: '/dpa', page: <LegalDocumentLayout kind="dpa" /> }],
  ['/cookies', { route: '/cookies', page: <LegalDocumentLayout kind="cookies" /> }],
])

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
}

function renderShell(page, route) {
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={[route]}>
      <QueryClientProvider client={createQueryClient()}>
        <div className="cronos-marketing">
          <MarketingHeader />
          <main>{page}</main>
          <MarketingFooter />
          <ScrollToTopButton />
        </div>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

export function renderPublicRoute(pathname) {
  const normalizedPath = pathname.length > 1 ? pathname.replace(/\/$/, '') : pathname
  const definition = routeDefinitions.get(normalizedPath)
  if (!definition) throw new Error(`Unknown public build route: ${pathname}`)
  return renderShell(definition.page, definition.route)
}

export function renderStaticNotFound() {
  return renderToStaticMarkup(<StaticNotFoundPage />)
}
