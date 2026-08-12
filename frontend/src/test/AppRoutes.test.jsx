import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from './testUtils'
import { resetClerkState, setClerkState } from './setup'
import { marketingMetadata } from '../features/marketing/content/metadata'
import App from '../App'

vi.mock('../features/members/data', async (importOriginal) => ({
  ...(await importOriginal()),
  useCurrentMember: () => ({
    data: { access_status: 'active', lifecycle_status: 'active', capabilities: ['admin'], default_mode: 'admin' },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
}))

function renderAppAt(path) {
  window.history.replaceState({}, '', path)
  return renderWithProviders(<App />)
}

describe('App route polish', () => {
  beforeEach(() => {
    resetClerkState()
    setClerkState({ isSignedIn: false, isLoaded: true })
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
  })

  it(
    'lazy-loads the signed-out marketing route through the shared fallback',
    async () => {
      const { container } = renderAppAt('/')
      expect(container.querySelector('.spinner-border')).toBeInTheDocument()
      expect(
        await screen.findByRole('heading', {
          name: /horários para o ensino profissional português/i,
        }, { timeout: 10_000 }),
      ).toBeInTheDocument()
    },
    10_000,
  )

  it('redirects a signed-in member from marketing to their default route', async () => {
    setClerkState({ isSignedIn: true })
    renderAppAt('/vantagens')
    await waitFor(() => expect(window.location.pathname).toBe('/dashboard'))

    const baseMetadata = marketingMetadata['/']
    await waitFor(() => {
      expect(document.title).toBe(baseMetadata.title)
      expect(document.querySelector('meta[name="description"]')).toHaveAttribute('content', baseMetadata.description)
      expect(document.querySelector('link[rel="canonical"]')).toHaveAttribute('href', baseMetadata.canonicalUrl)
      expect(document.querySelector('meta[property="og:title"]')).toHaveAttribute('content', baseMetadata.title)
      expect(document.querySelector('meta[property="og:description"]')).toHaveAttribute('content', baseMetadata.description)
      expect(document.querySelector('meta[property="og:url"]')).toHaveAttribute('content', baseMetadata.canonicalUrl)
      expect(document.querySelector('meta[name="twitter:title"]')).toHaveAttribute('content', baseMetadata.title)
      expect(document.querySelector('meta[name="twitter:description"]')).toHaveAttribute('content', baseMetadata.description)
    })
  })

  it('redirects /sign-in to /login', async () => {
    renderAppAt('/sign-in')

    await waitFor(() => {
      expect(window.location.pathname).toBe('/login')
    })
  })

  it('redirects /sign-up to /register', async () => {
    renderAppAt('/sign-up')

    await waitFor(() => {
      expect(window.location.pathname).toBe('/register')
    })
  })

  it('renders a friendly 404 for unknown routes', async () => {
    renderAppAt('/rota-inexistente')

    expect(await screen.findByRole('heading', { name: /página não encontrada/i })).toBeInTheDocument()
    expect(screen.getByText(/rota-inexistente/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /voltar ao início/i })).toHaveAttribute('href', '/')
  })
})
