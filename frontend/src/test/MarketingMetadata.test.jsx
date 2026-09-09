import { cleanup, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { marketingMetadata } from '../features/marketing/content/metadata'
import App from '../App'
import { renderWithProviders } from './testUtils'
import { resetClerkState, setClerkState } from './setup'

const publicRoutes = ['/', '/vantagens', '/como-funciona', '/sobre', '/ajuda', '/contacto', '/privacidade', '/termos', '/dpa', '/cookies']

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

    const canonicalUrls = Object.values(marketingMetadata).map(({ canonicalUrl }) => canonicalUrl)
    expect(new Set(canonicalUrls).size).toBe(publicRoutes.length)
    expect(canonicalUrls.every((url) => url.startsWith('https://cronos.pt'))).toBe(true)
    expect(publicRoutes.every((route) => marketingMetadata[route].canonicalUrl === `https://cronos.pt${route}`)).toBe(true)
  })
})
