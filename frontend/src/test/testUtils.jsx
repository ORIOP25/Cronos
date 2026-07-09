// Ficheiro: frontend/src/test/testUtils.jsx
/**
 * Utilitários de teste partilhados.
 * Fornece wrapper com QueryClientProvider.
 *
 * Para testes que precisam de routing, usa renderWithRouter()
 * ou adiciona MemoryRouter manualmente.
 */

import React from 'react'
import PropTypes from 'prop-types'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

/**
 * Cria um QueryClient novo por teste (evita state leak entre testes).
 */
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  })
}

/**
 * Renderiza componente com QueryClientProvider.
 * Usar para componentes que usam React Query hooks.
 * Para testes que precisam de routing, usar renderWithRouter().
 */
export function renderWithProviders(ui, options = {}) {
  const queryClient = options.queryClient || createTestQueryClient()

  function Wrapper({ children }) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    )
  }

  Wrapper.propTypes = {
    children: PropTypes.node,
  }

  const renderResult = render(ui, { wrapper: Wrapper, ...options })

  return {
    ...renderResult,
    queryClient,
  }
}

/**
 * Renderiza componente com todos os providers incluindo MemoryRouter.
 * Usar para testes de página/componente que precisam de routing.
 */
export function renderWithRouter(ui, { initialEntries = ['/'], ...options } = {}) {
  return renderWithProviders(
    <MemoryRouter initialEntries={initialEntries}>
      {ui}
    </MemoryRouter>,
    options
  )
}
