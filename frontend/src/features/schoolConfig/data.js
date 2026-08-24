import { useOrganization } from '@clerk/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import apiClient from '../../apiClient'
import { invalidateOrgQueries, orgQueryKey } from '../queryKeys'
import { invalidatePreparationQueries } from '../readiness/data'

const RESOURCES = {
  calendar: 'calendar-events',
  gridSettings: 'org-grid-settings',
  heatmap: 'heatmap',
  settings: 'org-settings',
}

const GRID_DEPENDENCIES = [
  RESOURCES.gridSettings,
  'timeslots',
  'my-availability',
  RESOURCES.heatmap,
  'weekSchedule',
  'dashboard',
  'scheduler-status',
  'scheduler-current-draft',
]

function useOrganizationId() {
  return useOrganization().organization?.id
}

export function useCalendarEvents() {
  const orgId = useOrganizationId()
  return useQuery({
    queryKey: orgQueryKey(RESOURCES.calendar, orgId),
    enabled: Boolean(orgId),
    queryFn: () => apiClient.get('/school/calendar-events/'),
  })
}

export function useSyncHolidays() {
  const orgId = useOrganizationId()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiClient.post('/school/settings/sync-holidays'),
    onSuccess: () => {
      void invalidateOrgQueries(queryClient, orgId, [RESOURCES.calendar])
      void invalidatePreparationQueries(queryClient, orgId)
    },
  })
}

export function useCreateCalendarEvent() {
  const orgId = useOrganizationId()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload) => apiClient.post('/school/calendar-events/', payload),
    onSuccess: () => {
      void invalidateOrgQueries(queryClient, orgId, [RESOURCES.calendar])
      void invalidatePreparationQueries(queryClient, orgId)
    },
  })
}

export function useDeleteCalendarEvent() {
  const orgId = useOrganizationId()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id) => apiClient.delete(`/school/calendar-events/${id}`),
    onSuccess: () => {
      void invalidateOrgQueries(queryClient, orgId, [RESOURCES.calendar])
      void invalidatePreparationQueries(queryClient, orgId)
    },
  })
}

export function useSchoolSettings() {
  const orgId = useOrganizationId()
  return useQuery({
    queryKey: orgQueryKey(RESOURCES.settings, orgId),
    enabled: Boolean(orgId),
    queryFn: () => apiClient.get('/school/settings/'),
  })
}

export function useSoftResetSchoolYear() {
  const orgId = useOrganizationId()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload) => apiClient.post('/school/settings/soft-reset', payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        predicate: (query) => query.queryKey[1] === orgId && query.queryKey[0] !== RESOURCES.settings,
      })
      void invalidatePreparationQueries(queryClient, orgId)
    },
  })
}

export function useUpsertSchoolSettings() {
  const orgId = useOrganizationId()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload) => apiClient.post('/school/settings/', payload),
    onSuccess: () => {
      void invalidateOrgQueries(queryClient, orgId, [RESOURCES.settings])
      void invalidatePreparationQueries(queryClient, orgId)
    },
  })
}

export function useGridSettings() {
  const orgId = useOrganizationId()
  return useQuery({
    queryKey: orgQueryKey(RESOURCES.gridSettings, orgId),
    enabled: Boolean(orgId),
    queryFn: async () => {
      try {
        return await apiClient.get('/school/grid-settings/')
      } catch (error) {
        if (error.response?.status === 404) return null
        throw error
      }
    },
  })
}

export function useRegenerateGrid() {
  const orgId = useOrganizationId()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload) => apiClient.post('/school/grid-settings/regenerate', payload),
    onSuccess: () => {
      void invalidateOrgQueries(queryClient, orgId, GRID_DEPENDENCIES)
      void invalidatePreparationQueries(queryClient, orgId)
    },
  })
}

export function useAvailabilityHeatmap() {
  const orgId = useOrganizationId()
  return useQuery({
    queryKey: orgQueryKey(RESOURCES.heatmap, orgId),
    enabled: Boolean(orgId),
    queryFn: () => apiClient.get('/analytics/availability-heatmap'),
  })
}
