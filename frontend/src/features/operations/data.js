import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useApiClient } from '../../ApiClientContext'
import { invalidatePreparationQueries } from '../readiness/data'
import { invalidateOrgQueries, orgQueryKey } from '../queryKeys'
import { useOrganization, useAuth } from '@clerk/react'

const DYNAMIC_OPTS = {
  staleTime: 1000 * 60 * 5, // 5 minutos de "frescura"
}

export const useOccurrences = ({ classId, dateFrom, dateTo, status, enabled = true } = {}) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  const params = {}
  if (classId) params.class_id = classId
  if (dateFrom) params.date_from = dateFrom
  if (dateTo) params.date_to = dateTo
  if (status) params.status = status

  return useQuery({
    queryKey: orgQueryKey('occurrences', orgId, classId, dateFrom, dateTo, status),
    queryFn: async () => {
      const data = await apiClient.get('/occurrences/', { params })
      if (Array.isArray(data)) return { items: data, total: data.length, limit: data.length, offset: 0 }
      return { items: data.items ?? [], total: data.total ?? 0, limit: data.limit ?? 100, offset: data.offset ?? 0 }
    },
    enabled: Boolean(orgId) && enabled,
    ...DYNAMIC_OPTS,
  })
}

/**
 * Lista de dívidas de horas agrupadas por turma/disciplina.
 */
export const useDebts = ({ classId } = {}) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  const params = {}
  if (classId) params.class_id = classId

  return useQuery({
    queryKey: orgQueryKey('debts', orgId, classId),
    queryFn: () => apiClient.get('/occurrences/debts', { params }),
    enabled: Boolean(orgId),
    ...DYNAMIC_OPTS,
  })
}


/**
 * Ranking de recomendações para uma ocorrência específica.
 */
export const useSubstituteRecommendations = ({ occurrenceId } = {}) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: orgQueryKey('substitute-recommendations', orgId, occurrenceId),
    queryFn: async () => {
      return apiClient.get(`/occurrences/${occurrenceId}/substitutes/recommendations`)
    },
    enabled: Boolean(orgId) && Boolean(occurrenceId),
    ...DYNAMIC_OPTS,
  })
}

/**
 * Mutation para registar falta (GAP) ou substituição (SUBSTITUTED).
 */
export const useUpdateOccurrence = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ id, status, version, substituteTeacherId, substituteSubjectId }) => {
      return apiClient.patch(`/occurrences/${id}`, {
        status,
        version,
        substitute_teacher_id: substituteTeacherId ?? null,
        substitute_subject_id: substituteSubjectId ?? null,
      })
    },
    onSuccess: () => {
      void invalidateOrgQueries(queryClient, orgId, ['occurrences', 'debts', 'weekSchedule', 'classes', 'substitute-recommendations', 'substitute-diagnostics', 'dashboard', 'teacher-progress', 'my-timesheet', 'timesheets'])
    },
  })
}

/**
 * Cancelar uma ocorrência (OPEN ou decidida), revertendo LessonLog → PENDING.
 * WBS V3 Fase 3.
 */
export const useCancelOccurrence = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ id, version, cancelCompletedSubstituteLog = false }) => {
      return apiClient.post(`/occurrences/${id}/cancel`, {
        version,
        cancel_completed_substitute_log: cancelCompletedSubstituteLog,
      })
    },
    onSuccess: () => {
      void invalidateOrgQueries(queryClient, orgId, ['occurrences', 'debts', 'weekSchedule', 'classes', 'substitute-diagnostics', 'dashboard', 'teacher-progress', 'my-timesheet', 'timesheets'])
    },
  })
}

/**
 * Registar execução de aula (LessonLog).
 */
export const useUpsertLessonLog = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ operationalBlockId, schedulerLessonId, payload }) => {
      let endpoint
      if (schedulerLessonId) {
        endpoint = `/schedule/lessons/${schedulerLessonId}/log`
      } else if (operationalBlockId) {
        endpoint = `/schedule/operational-blocks/${operationalBlockId}/log`
      } else {
        throw new Error('Não foi possível identificar a aula deste registo.')
      }
      return apiClient.put(endpoint, payload)
    },
    onSuccess: () => {
      void invalidateOrgQueries(queryClient, orgId, ['weekSchedule', 'classes', 'occurrences', 'debts', 'dashboard', 'teacher-progress', 'my-timesheet', 'timesheets'])
    },
  })
}

// ============================================================
//  Fase 3 — Timesheets (Fecho Semanal)
// ============================================================

export const useMyTimesheet = (weekStartDate) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: orgQueryKey('my-timesheet', orgId, weekStartDate),
    queryFn: async () => {
      return apiClient.get(`/timesheets/me/${weekStartDate}`)
    },
    enabled: Boolean(orgId) && Boolean(weekStartDate),
    ...DYNAMIC_OPTS,
  })
}

export const useSubmitMyTimesheet = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async (weekStartDate) => {
      return apiClient.post(`/timesheets/me/${weekStartDate}/submit`)
    },
    onSuccess: (_, weekStartDate) => {
      void queryClient.invalidateQueries({ queryKey: orgQueryKey('my-timesheet', orgId, weekStartDate) })
      void invalidateOrgQueries(queryClient, orgId, ['weekSchedule'])
    },
  })
}

export const useTimesheets = (weekStartDate, status) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  const params = {}
  if (weekStartDate) params.week_start_date = weekStartDate
  if (status) params.status = status

  return useQuery({
    queryKey: orgQueryKey('timesheets', orgId, weekStartDate, status),
    queryFn: () => apiClient.get('/timesheets/', { params }),
    enabled: Boolean(orgId),
    ...DYNAMIC_OPTS,
  })
}

export const useUpdateTimesheetStatus = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ timesheetId, status }) => {
      return apiClient.patch(`/timesheets/${timesheetId}/status`, { status })
    },
    onSuccess: () => {
      void invalidateOrgQueries(queryClient, orgId, ['timesheets', 'my-timesheet'])
      void queryClient.refetchQueries({ queryKey: orgQueryKey('weekSchedule', orgId), type: 'active' })
    },
  })
}

// ============================================================
//  Sprint 3 — Rascunhos e Diff de Horários
// ============================================================

/**
 * Lista rascunhos pendentes de aprovação para a organização do user.
 */
export const useDashboard = ({ enabled = true } = {}) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: orgQueryKey('dashboard', orgId),
    queryFn: async () => {
      const data = await apiClient.get('/dashboard')
      if (!data || !['PREPARATION', 'OPERATIONAL'].includes(data.mode)) {
        throw new Error('Dashboard contract error: mode is missing or unknown.')
      }
      if (data.mode === 'PREPARATION' && (!data.bases || typeof data.bases !== 'object')) {
        throw new Error('Dashboard contract error: preparation bases are missing.')
      }
      if (data.mode === 'PREPARATION' && (!data.prevalidation || typeof data.prevalidation !== 'object')) {
        throw new Error('Dashboard contract error: preparation prevalidation is missing.')
      }
      return data
    },
    enabled: Boolean(orgId) && enabled,
    ...DYNAMIC_OPTS,
    refetchOnWindowFocus: false,
  })
}

/**
 * Progresso curricular do professor autenticado.
 * Retorna turmas com disciplinas e módulos + progresso.
 */
export const useTeacherProgress = ({ enabled = true } = {}) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: orgQueryKey('teacher-progress', orgId),
    queryFn: async () => {
      return apiClient.get('/teachers/me/progress')
    },
    enabled: Boolean(orgId) && enabled,
    ...DYNAMIC_OPTS,
  })
}

/**
 * Disponibilidade do professor autenticado.
 */
export const useMyAvailability = ({ enabled = true } = {}) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  const { isLoaded } = useAuth()
  return useQuery({
    queryKey: orgQueryKey('my-availability', orgId),
    queryFn: async () => {
      return apiClient.get('/teachers/me/availability')
    },
    enabled: Boolean(orgId) && isLoaded && enabled,
  })
}

/**
 * Guardar disponibilidade do professor.
 */
export const useSaveAvailability = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id
  return useMutation({
    mutationFn: async ({ payload }) => {
      return apiClient.put('/teachers/me/availability', payload)
    },
    onSuccess: (_, { payload }) => {
      queryClient.setQueryData(orgQueryKey('my-availability', orgId), payload)
      void invalidateOrgQueries(queryClient, orgId, ['my-availability'])
      void invalidatePreparationQueries(queryClient, orgId)
    },
  })
}

/**
 * Disponibilidade de um professor vista pela Direção.
 */
export const useTeacherAvailability = ({ teacherId, onDate } = {}) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: orgQueryKey('teacher-availability', orgId, teacherId, onDate ?? null),
    queryFn: async () => apiClient.get(`/teachers/${teacherId}/availability`, {
      params: onDate ? { on_date: onDate } : {},
    }),
    enabled: Boolean(orgId) && Boolean(teacherId),
    ...DYNAMIC_OPTS,
  })
}

/**
 * Direção edita a disponibilidade de um professor sem convite.
 */
export const useSaveTeacherAvailability = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id
  return useMutation({
    mutationFn: async ({ teacherId, payload, onDate }) => {
      return apiClient.put(`/teachers/${teacherId}/availability`, payload, {
        params: onDate ? { on_date: onDate } : {},
      })
    },
    onSuccess: (_, { teacherId, payload, onDate }) => {
      queryClient.setQueryData(orgQueryKey('teacher-availability', orgId, teacherId, onDate ?? null), payload)
      void invalidateOrgQueries(queryClient, orgId, [
        'teacher-availability',
        'substitute-recommendations',
        'substitute-diagnostics',
        'occurrences',
        'dashboard',
        'teacher-progress',
      ])
      void invalidatePreparationQueries(queryClient, orgId)
    },
  })
}

/**
 * Diagnóstico estruturado de candidatos a substituto.
 */
export const useSubstituteDiagnostics = ({ occurrenceId } = {}) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: orgQueryKey('substitute-diagnostics', orgId, occurrenceId),
    queryFn: async () => (
      apiClient.get(`/occurrences/${occurrenceId}/substitutes/diagnostics`)
    ),
    enabled: Boolean(orgId) && Boolean(occurrenceId),
    ...DYNAMIC_OPTS,
  })
}
