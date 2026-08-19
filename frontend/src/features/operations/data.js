import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../../apiClient'
import { useOrganization, useAuth } from '@clerk/react'

const DYNAMIC_OPTS = {
  staleTime: 1000 * 60 * 5, // 5 minutos de "frescura"
}

export const useOccurrences = ({ classId, dateFrom, dateTo, status } = {}) => {
  const orgId = useOrganization().organization?.id
  const params = {}
  if (classId) params.class_id = classId
  if (dateFrom) params.date_from = dateFrom
  if (dateTo) params.date_to = dateTo
  if (status) params.status = status

  return useQuery({
    queryKey: ['occurrences', orgId, classId, dateFrom, dateTo, status],
    queryFn: async () => {
      const data = await apiClient.get('/occurrences/', { params })
      if (Array.isArray(data)) return { items: data, total: data.length, limit: data.length, offset: 0 }
      return { items: data.items ?? [], total: data.total ?? 0, limit: data.limit ?? 100, offset: data.offset ?? 0 }
    },
    enabled: Boolean(orgId),
    ...DYNAMIC_OPTS,
  })
}

/**
 * Lista de dívidas de horas agrupadas por turma/disciplina.
 */
export const useDebts = ({ classId } = {}) => {
  const orgId = useOrganization().organization?.id
  const params = {}
  if (classId) params.class_id = classId

  return useQuery({
    queryKey: ['debts', orgId, classId],
    queryFn: () => apiClient.get('/occurrences/debts', { params }),
    enabled: Boolean(orgId),
    ...DYNAMIC_OPTS,
  })
}


/**
 * Ranking de recomendações para uma ocorrência específica.
 */
export const useSubstituteRecommendations = ({ occurrenceId } = {}) => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['substitute-recommendations', orgId, occurrenceId],
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
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ id, status, version, reason, substituteTeacherId, substituteSubjectId }) => {
      return apiClient.patch(`/occurrences/${id}`, {
        status,
        version,
        reason,
        substitute_teacher_id: substituteTeacherId ?? null,
        substitute_subject_id: substituteSubjectId ?? null,
      })
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['occurrences', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['debts', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['weekSchedule', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['classes', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['substitute-recommendations', orgId] })
    },
  })
}

/**
 * Cancelar uma ocorrência (OPEN ou decidida), revertendo LessonLog → PENDING.
 * WBS V3 Fase 3.
 */
export const useCancelOccurrence = () => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ id, version, reason, cancelCompletedSubstituteLog = false }) => {
      return apiClient.post(`/occurrences/${id}/cancel`, {
        version,
        reason,
        cancel_completed_substitute_log: cancelCompletedSubstituteLog,
      })
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['occurrences', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['debts', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['weekSchedule', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['my-timesheet', orgId] })
    },
  })
}

/**
 * Registar execução de aula (LessonLog).
 */
export const useUpsertLessonLog = () => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ activeScheduleBlockId, operationalBlockId, payload }) => {
      const endpoint = operationalBlockId
        ? `/schedule/operational-blocks/${operationalBlockId}/log`
        : `/schedule/active-blocks/${activeScheduleBlockId}/log`
      return apiClient.put(endpoint, payload)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['weekSchedule', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['classes', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['occurrences', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['debts', orgId] })
    },
  })
}

// ============================================================
//  Fase 3 — Timesheets (Fecho Semanal)
// ============================================================

export const useMyTimesheet = (weekStartDate) => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['my-timesheet', orgId, weekStartDate],
    queryFn: async () => {
      return apiClient.get(`/timesheets/me/${weekStartDate}`)
    },
    enabled: Boolean(orgId) && Boolean(weekStartDate),
    ...DYNAMIC_OPTS,
  })
}

export const useSubmitMyTimesheet = () => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async (weekStartDate) => {
      return apiClient.post(`/timesheets/me/${weekStartDate}/submit`)
    },
    onSuccess: (_, weekStartDate) => {
      void queryClient.invalidateQueries({ queryKey: ['my-timesheet', orgId, weekStartDate] })
      void queryClient.invalidateQueries({ queryKey: ['weekSchedule', orgId] })
    },
  })
}

export const useTimesheets = (weekStartDate, status) => {
  const orgId = useOrganization().organization?.id
  const params = {}
  if (weekStartDate) params.week_start_date = weekStartDate
  if (status) params.status = status

  return useQuery({
    queryKey: ['timesheets', orgId, weekStartDate, status],
    queryFn: () => apiClient.get('/timesheets/', { params }),
    enabled: Boolean(orgId),
    ...DYNAMIC_OPTS,
  })
}

export const useUpdateTimesheetStatus = () => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ timesheetId, status }) => {
      return apiClient.patch(`/timesheets/${timesheetId}/status`, { status })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['timesheets', orgId] })
      queryClient.refetchQueries({ queryKey: ['weekSchedule', orgId], type: 'active' })
      queryClient.invalidateQueries({ queryKey: ['my-timesheet', orgId] })
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
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['dashboard', orgId],
    queryFn: async () => {
      return apiClient.get('/dashboard')
    },
    enabled: Boolean(orgId) && enabled,
    ...DYNAMIC_OPTS,
  })
}

/**
 * Progresso curricular do professor autenticado.
 * Retorna turmas com disciplinas e módulos + progresso.
 */
export const useTeacherProgress = ({ enabled = true } = {}) => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['teacher-progress', orgId],
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
  const orgId = useOrganization().organization?.id
  const { isLoaded } = useAuth()
  return useQuery({
    queryKey: ['my-availability', orgId],
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
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id
  return useMutation({
    mutationFn: async ({ teacherId, payload }) => {
      return apiClient.post(`/teachers/${teacherId}/availability`, payload)
    },
    onSuccess: (_, { payload }) => {
      queryClient.setQueryData(['my-availability', orgId], payload)
      void queryClient.invalidateQueries({ queryKey: ['my-availability', orgId] })
    },
  })
}
