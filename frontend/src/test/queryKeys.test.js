import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import { invalidateOrgQueries, orgQueryKey } from '../features/queryKeys'

describe('organization query helpers', () => {
  it('builds resource, organization, and scope keys in that order', () => {
    expect(orgQueryKey('calendar-events', 'org_a', '2026')).toEqual([
      'calendar-events',
      'org_a',
      '2026',
    ])
  })

  it('invalidates only requested roots for the selected organization', async () => {
    const queryClient = new QueryClient()
    const keys = {
      settingsA: orgQueryKey('org-settings', 'org_a'),
      calendarA: orgQueryKey('calendar-events', 'org_a', '2026'),
      heatmapA: orgQueryKey('heatmap', 'org_a'),
      settingsB: orgQueryKey('org-settings', 'org_b'),
    }
    Object.values(keys).forEach((key) => queryClient.setQueryData(key, {}))

    await invalidateOrgQueries(queryClient, 'org_a', ['org-settings', 'calendar-events'])

    expect(queryClient.getQueryState(keys.settingsA).isInvalidated).toBe(true)
    expect(queryClient.getQueryState(keys.calendarA).isInvalidated).toBe(true)
    expect(queryClient.getQueryState(keys.heatmapA).isInvalidated).toBe(false)
    expect(queryClient.getQueryState(keys.settingsB).isInvalidated).toBe(false)
  })
})
