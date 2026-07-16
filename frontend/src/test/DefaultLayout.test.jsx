import { describe, it, expect, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { renderWithProviders } from './testUtils'
import { setClerkState } from './setup'
import DefaultLayout from '../components/DefaultLayout'

vi.mock('../hooks/useRole', () => ({
  useRole: () => ({ isAdmin: true, isTeacher: false }),
}))

describe('DefaultLayout', () => {
  it('renders navigation, account actions, and nested route content', () => {
    setClerkState({ role: 'org:admin', orgId: 1, orgName: 'Escola Teste', isSignedIn: true })
    const { getByRole, getByText, getByTestId } = renderWithProviders(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route element={<DefaultLayout />}>
            <Route path="/dashboard" element={<span data-testid="child">Content</span>} />
          </Route>
        </Routes>
      </MemoryRouter>
    )
    expect(getByRole('navigation')).toBeInTheDocument()
    expect(getByText('Dashboard')).toBeInTheDocument()
    expect(getByText('Equipa')).toBeInTheDocument()
    expect(getByRole('button', { name: /terminar sessão/i })).toBeInTheDocument()
    expect(getByTestId('child')).toHaveTextContent('Content')
  })
})
