// Ficheiro: frontend/src/test/testUtils.jsx
/**
 * Utilitários de teste partilhados.
 * Fornece wrapper com QueryClientProvider para componentes que usam React Query.
 */

import React from 'react'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

/**
 * Cria um QueryClient novo por teste (evita state leak entre testes).
 */
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,       // Não repetir queries em testes
        gcTime: 0,          // Não guardar cache
      },
    },
  })
}

/**
 * Renderiza componente com QueryClientProvider.
 * Usar em vez de `render()` quando o componente usa hooks React Query.
 */
export function renderWithProviders(ui, options = {}) {
  const queryClient = createTestQueryClient()

  function Wrapper({ children }) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    )
  }

  return render(ui, { wrapper: Wrapper, ...options })
}
