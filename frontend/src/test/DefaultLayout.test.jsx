import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { renderWithProviders } from './testUtils'
import { setClerkState } from './setup'
import DefaultLayout from '../components/DefaultLayout'

vi.mock('../hooks/useSchoolData', () => ({
  useDashboard: () => ({ data: null, isLoading: false }),
}))

describe('DefaultLayout', () => {
  it('can be imported without errors', () => {
    expect(typeof DefaultLayout).toBe('function')
  })

  it('renders with Router and Clerk mock', () => {
    setClerkState({ role: 'org:admin', orgId: 1, orgName: 'Escola Teste', isSignedIn: true })
    const { container } = renderWithProviders(
      <MemoryRouter initialEntries={['/dashboard']}>
        <DefaultLayout><span data-testid="child">Content</span></DefaultLayout>
      </MemoryRouter>
    )
    expect(container).toBeTruthy()
  })
})
