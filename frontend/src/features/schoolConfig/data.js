import { useOrganization } from '@clerk/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import apiClient from '../../apiClient'
import { invalidateOrgQueries, orgQueryKey } from '../queryKeys'
import { invalidatePreparationQueries } from '../readiness/data'

const RESOURCES = {
  calendar: 'calendar-events',
  gridChangesPending: 'grid-change-pending',
  gridConfiguration: 'grid-configuration',
  gridSettings: 'org-grid-settings',
  heatmap: 'heatmap',
  settings: 'org-settings',
}

const CALENDAR_DEPENDENCIES = [
  RESOURCES.calendar,
  'weekSchedule',
  'scheduler-status',
  'scheduler-current-draft',
  'occurrences',
]

const GRID_DEPENDENCIES = [
  RESOURCES.gridSettings,
  RESOURCES.gridConfiguration,
  RESOURCES.gridChangesPending,
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

export function useCreateCalendarEvent() {
  const orgId = useOrganizationId()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload) => apiClient.post('/school/calendar-events/', payload),
    onSuccess: () => {
      void invalidateOrgQueries(queryClient, orgId, CALENDAR_DEPENDENCIES)
      void invalidatePreparationQueries(queryClient, orgId)
    },
  })
}

export function usePreviewCalendarEventChange() {
  return useMutation({
    mutationFn: (payload) => apiClient.post('/school/calendar-events/preview', payload),
  })
}

export function useUpdateCalendarEvent() {
  const orgId = useOrganizationId()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...payload }) => apiClient.put(`/school/calendar-events/${id}`, payload),
    onSuccess: () => {
      void invalidateOrgQueries(queryClient, orgId, CALENDAR_DEPENDENCIES)
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
      void invalidateOrgQueries(queryClient, orgId, CALENDAR_DEPENDENCIES)
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
    onSuccess: (data) => {
      queryClient.setQueryData(orgQueryKey(RESOURCES.settings, orgId), data)
      void invalidateOrgQueries(queryClient, orgId, [RESOURCES.settings, RESOURCES.calendar])
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

export function useGridConfiguration() {
  const orgId = useOrganizationId()
  return useQuery({
    queryKey: orgQueryKey(RESOURCES.gridConfiguration, orgId),
    enabled: Boolean(orgId),
    queryFn: () => apiClient.get('/school/grid-configuration/'),
  })
}

export function useGridChangePending() {
  const orgId = useOrganizationId()
  return useQuery({
    queryKey: orgQueryKey(RESOURCES.gridChangesPending, orgId),
    enabled: Boolean(orgId),
    queryFn: () => apiClient.get('/school/grid-changes/pending'),
  })
}

export function useGridChangePreview() {
  return useMutation({
    mutationFn: (payload) => apiClient.post('/school/grid-changes/preview', payload),
  })
}

export function useGridChangePropose() {
  const orgId = useOrganizationId()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload) => apiClient.post('/school/grid-changes', payload),
    onSuccess: () => {
      void invalidateOrgQueries(queryClient, orgId, GRID_DEPENDENCIES)
      void invalidatePreparationQueries(queryClient, orgId)
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
