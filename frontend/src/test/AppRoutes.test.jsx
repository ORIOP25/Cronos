import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from './testUtils'
import { resetClerkState, setClerkState } from './setup'
import { marketingMetadata } from '../features/marketing/content/metadata'
import App from '../App'

vi.mock('../features/members/data', async (importOriginal) => ({
  ...(await importOriginal()),
  useCurrentMember: () => ({
    data: {
      access_status: 'active',
      lifecycle_status: 'active',
      capabilities: ['admin'],
      default_mode: 'admin',
      foundation_status: 'COMPLETED',
    },
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
  const initialHeadHtml = `
    <title>Fixture title</title>
    <meta name="description" content="Fixture description" />
    <link rel="canonical" href="https://cronos.pt/" />
    <meta property="og:title" content="Fixture title" />
    <meta property="og:description" content="Fixture description" />
    <meta property="og:url" content="https://cronos.pt/" />
    <meta name="twitter:title" content="Fixture title" />
    <meta name="twitter:description" content="Fixture description" />
  `

  beforeEach(() => {
    resetClerkState()
    vi.clearAllMocks()
    setClerkState({ isSignedIn: false, isLoaded: true })
    document.head.innerHTML = initialHeadHtml
  })

  afterEach(() => {
    resetClerkState()
    vi.clearAllMocks()
    document.head.innerHTML = initialHeadHtml
  })

  it(
    'lazy-loads the signed-out marketing route through the shared fallback',
    async () => {
      const { container } = renderAppAt('/')
      expect(container.querySelector('.spinner-border')).toBeInTheDocument()
      expect(
        await screen.findByRole('heading', {
          name: /gestão de horários para o ensino profissional/i,
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

  it('renders the cookies document as a standalone legal page', async () => {
    renderAppAt('/cookies')

    expect(await screen.findByRole('heading', { name: /cookies e armazenamento local/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /cookies estritamente necessários/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /voltar ao cronos/i })).toHaveAttribute('href', '/')
  })

  it('renders every DPA annex referenced by the agreement', async () => {
    renderAppAt('/dpa')

    expect(await screen.findByRole('heading', { name: /acordo de tratamento de dados/i })).toBeInTheDocument()
    for (const annex of ['Anexo A — Subprocessadores', 'Anexo B — Medidas de segurança', 'Anexo C — Transferências internacionais', 'Anexo D — Instruções documentadas']) {
      expect(screen.getByRole('heading', { name: annex })).toBeInTheDocument()
    }
  })

  it('does not expose the removed onboarding route', async () => {
    renderAppAt('/onboarding')

    expect(await screen.findByRole('heading', { name: /página não encontrada/i })).toBeInTheDocument()
  })
})
