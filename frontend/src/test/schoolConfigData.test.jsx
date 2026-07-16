import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { resetClerkState, setClerkState } from './setup'
import { renderWithProviders } from './testUtils'
import {
  useAvailabilityHeatmap,
  useCalendarEvents,
  useSchoolSettings,
  useSoftResetSchoolYear,
} from '../features/schoolConfig/data'

vi.mock('../apiClient', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

import apiClient from '../apiClient'

let activeOrgId

function SchoolConfigDataProbe() {
  const settings = useSchoolSettings()
  const calendar = useCalendarEvents()
  const heatmap = useAvailabilityHeatmap()

  return (
    <output>
      {settings.data?.organization}
      {calendar.data?.[0]?.organization}
      {heatmap.data?.[0]?.organization}
    </output>
  )
}

function SoftResetProbe() {
  const softReset = useSoftResetSchoolYear()
  return <button onClick={() => softReset.mutate({ confirm_phrase: 'Confirmo' })}>Reset</button>
}

describe('school configuration data hooks', () => {
  beforeEach(() => {
    resetClerkState()
    vi.clearAllMocks()
    activeOrgId = 'org-a'
    setClerkState({ orgId: activeOrgId })
    apiClient.get.mockImplementation(() => Promise.resolve([
      { organization: activeOrgId },
    ]))
    apiClient.post.mockResolvedValue({ message: 'ok' })
  })

  it('changes settings, calendar, and heatmap data when the active organization changes', async () => {
    apiClient.get.mockImplementation((url) => Promise.resolve(
      url === '/school/settings/'
        ? { organization: activeOrgId }
        : [{ organization: activeOrgId }],
    ))

    const view = renderWithProviders(<SchoolConfigDataProbe />)

    expect(await screen.findByText('org-aorg-aorg-a')).toBeInTheDocument()

    activeOrgId = 'org-b'
    setClerkState({ orgId: activeOrgId })
    view.rerender(<SchoolConfigDataProbe />)

    expect(await screen.findByText('org-borg-borg-b')).toBeInTheDocument()
    expect(screen.queryByText('org-aorg-aorg-a')).not.toBeInTheDocument()
    expect(apiClient.get.mock.calls.map(([url]) => url)).toEqual([
      '/school/settings/',
      '/school/calendar-events/',
      '/analytics/availability-heatmap',
      '/school/settings/',
      '/school/calendar-events/',
      '/analytics/availability-heatmap',
    ])
  })

  it('does not request organization data until an organization is active', async () => {
    setClerkState({ orgId: null })

    renderWithProviders(<SchoolConfigDataProbe />)

    await waitFor(() => expect(apiClient.get).not.toHaveBeenCalled())
  })

  it('resets only queries belonging to the active organization after a soft reset', async () => {
    const { queryClient } = renderWithProviders(<SoftResetProbe />)
    const resetQueries = vi.spyOn(queryClient, 'resetQueries')

    fireEvent.click(screen.getByRole('button', { name: 'Reset' }))

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(
      '/school/settings/soft-reset',
      { confirm_phrase: 'Confirmo' },
    ))
    await waitFor(() => expect(resetQueries).toHaveBeenCalledOnce())

    const { predicate } = resetQueries.mock.calls[0][0]
    expect(predicate({ queryKey: ['org-settings', 'org-a'] })).toBe(true)
    expect(predicate({ queryKey: ['calendar-events', 'org-b'] })).toBe(false)
    expect(predicate({ queryKey: ['unscoped'] })).toBe(false)
  })
})
