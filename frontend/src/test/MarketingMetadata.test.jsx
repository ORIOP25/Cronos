import { cleanup, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { canonicalMarketingRoutes, marketingMetadata } from '../features/marketing/content/metadata'
import App from '../App'
import { renderWithProviders } from './testUtils'
import { resetClerkState, setClerkState } from './setup'

const publicRoutes = [...canonicalMarketingRoutes, '/about', '/contact', '/privacy']

function installMetadataFixture() {
  document.head.innerHTML = `
    <title>Fixture title</title>
    <meta name="description" content="Fixture description" />
    <link rel="canonical" href="https://cronos.pt/" />
    <meta property="og:title" content="Fixture title" />
    <meta property="og:description" content="Fixture description" />
    <meta property="og:url" content="https://cronos.pt/" />
    <meta name="twitter:title" content="Fixture title" />
    <meta name="twitter:description" content="Fixture description" />
  `
}

describe('marketing metadata', () => {
  beforeEach(() => {
    resetClerkState()
    setClerkState({ isSignedIn: false, isLoaded: true })
    installMetadataFixture()
  })

  afterEach(() => cleanup())

  it('emits the metadata for every public route during SPA navigation', async () => {
    for (const route of publicRoutes) {
      window.history.replaceState({}, '', route)
      renderWithProviders(<App />)

      await screen.findByRole('heading', { level: 1 }, { timeout: 10_000 })
      const expected = marketingMetadata[route]

      await waitFor(() => {
        expect(document.title).toBe(expected.title)
        expect(document.querySelector('meta[name="description"]')).toHaveAttribute('content', expected.description)
        expect(document.querySelector('link[rel="canonical"]')).toHaveAttribute('href', expected.canonicalUrl)
        expect(document.querySelector('meta[property="og:title"]')).toHaveAttribute('content', expected.title)
        expect(document.querySelector('meta[property="og:description"]')).toHaveAttribute('content', expected.description)
        expect(document.querySelector('meta[property="og:url"]')).toHaveAttribute('content', expected.canonicalUrl)
        expect(document.querySelector('meta[name="twitter:title"]')).toHaveAttribute('content', expected.title)
        expect(document.querySelector('meta[name="twitter:description"]')).toHaveAttribute('content', expected.description)
      })

      cleanup()
      installMetadataFixture()
    }
  }, 30_000)

  it('keeps public routes and canonicals one-to-one', () => {
    expect(Object.keys(marketingMetadata)).toEqual(publicRoutes)

    const canonicalUrls = canonicalMarketingRoutes.map((route) => marketingMetadata[route].canonicalUrl)
    expect(new Set(canonicalUrls).size).toBe(canonicalMarketingRoutes.length)
    expect(canonicalUrls.every((url) => url.startsWith('https://cronos.pt'))).toBe(true)
    expect(canonicalMarketingRoutes.every((route) => marketingMetadata[route].canonicalUrl === `https://cronos.pt${route}`)).toBe(true)
    expect(marketingMetadata['/about'].canonicalUrl).toBe('https://cronos.pt/sobre')
    expect(marketingMetadata['/contact'].canonicalUrl).toBe('https://cronos.pt/contacto')
    expect(marketingMetadata['/privacy'].canonicalUrl).toBe('https://cronos.pt/privacidade')
  })
})
