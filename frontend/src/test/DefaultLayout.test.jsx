import { readFileSync } from 'node:fs'
import { describe, it, expect, vi } from 'vitest'
import { fireEvent, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { renderWithProviders } from './testUtils'
import { setClerkState } from './setup'
import DefaultLayout from '../components/DefaultLayout'
import { publicAsset } from '../utils/publicAsset'

const roleState = vi.hoisted(() => ({ isAdmin: true, isTeacher: false }))

vi.mock('../hooks/useRole', () => ({ useRole: () => roleState }))

const appShellCss = readFileSync('src/styles/app-shell.css', 'utf8')

describe('DefaultLayout', () => {
  it('renders navigation, account actions, and nested route content', () => {
    roleState.isAdmin = true
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
    expect(getByText('Painel')).toBeInTheDocument()
    expect(getByText('Equipa')).toBeInTheDocument()
    expect(getByRole('button', { name: /terminar sessão/i })).toBeInTheDocument()
    expect(getByTestId('child')).toHaveTextContent('Content')
  })

  it('renders the requested demo navigation before the member role is available', () => {
    roleState.isAdmin = false
    const { getByText } = renderWithProviders(
      <MemoryRouter>
        <DefaultLayout navigationRole="admin"><span>Demo</span></DefaultLayout>
      </MemoryRouter>
    )
    expect(getByText('Painel')).toBeInTheDocument()
    expect(getByText('Disciplinas')).toBeInTheDocument()
  })

  it('stacks the logo and toggle when the desktop sidebar is collapsed', () => {
    roleState.isAdmin = true
    localStorage.removeItem('hz-sidebar-collapsed')
    const { getByRole } = renderWithProviders(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route element={<DefaultLayout />}>
            <Route path="/dashboard" element={<span>Content</span>} />
          </Route>
        </Routes>
      </MemoryRouter>
    )

    const sidebar = getByRole('complementary', { name: 'Navegação principal' })
    const appSidebar = sidebar.querySelector('.app-sidebar')
    const brandRow = appSidebar.querySelector('.app-sidebar__brand-row')
    fireEvent.click(within(sidebar).getByRole('button', { name: 'Colapsar menu' }))

    expect(within(sidebar).getByRole('button', { name: 'Expandir menu' })).toBeVisible()
    expect(appSidebar).toHaveClass('is-collapsed')
    const logo = within(sidebar).getByRole('img', { name: 'Cronos' })
    expect(logo).toBeVisible()
    expect(logo).toHaveAttribute('src', publicAsset('/logo-white.png'))
    expect(brandRow.children[0]).toContainElement(logo)
    expect(brandRow.children[1]).toContainElement(within(sidebar).getByRole('button', { name: 'Expandir menu' }))
    expect(appShellCss).toMatch(/\.app-sidebar\.is-collapsed \.app-sidebar__brand-row\s*\{[^}]*flex-direction:\s*column[^}]*gap:\s*8px/)
  })
})
