import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import AppToaster from '../components/AppToaster'

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  })
}

export function renderWithProviders(ui, {
  queryClient = createTestQueryClient(),
  withToaster = false,
  ...renderOptions
} = {}) {
  function Wrapper({ children }) {
    return (
      <QueryClientProvider client={queryClient}>
        {withToaster && <AppToaster />}
        {children}
      </QueryClientProvider>
    )
  }

  return {
    ...render(ui, { wrapper: Wrapper, ...renderOptions }),
    queryClient,
  }
}

export function renderWithRouter(ui, {
  initialEntries = ['/'],
  ...renderOptions
} = {}) {
  return renderWithProviders(
    <MemoryRouter initialEntries={initialEntries}>
      {ui}
    </MemoryRouter>,
    renderOptions,
  )
}
