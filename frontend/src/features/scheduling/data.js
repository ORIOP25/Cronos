import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useApiClient } from '../../ApiClientContext'
import { invalidatePreparationQueries } from '../readiness/data'
import { useOrganization, useAuth } from '@clerk/react'

const DYNAMIC_OPTS = {
  staleTime: 1000 * 60 * 5, // 5 minutos de "frescura"
}

export const useSchedulerStatus = () => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  const { isLoaded } = useAuth()
  return useQuery({
    queryKey: ['scheduler-status', orgId],
    queryFn: async () => {
      return apiClient.get('/scheduler/status')
    },
    enabled: Boolean(orgId) && isLoaded,
    ...DYNAMIC_OPTS,
  })
}

export const useCurrentDraftSummary = (enabled = true) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  const { isLoaded } = useAuth()
  return useQuery({
    queryKey: ['scheduler-current-draft', orgId],
    queryFn: async () => {
      return apiClient.get('/scheduler/drafts/current')
    },
    enabled: Boolean(orgId) && isLoaded && enabled,
    ...DYNAMIC_OPTS,
  })
}

/**
 * Diff entre um rascunho e o horário ativo.
 */
export const useScheduleDiff = (draftId, enabled = true) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['schedule-diff', orgId, draftId],
    queryFn: async () => {
      return apiClient.get(`/scheduler/drafts/${draftId}/diff`)
    },
    enabled: Boolean(orgId) && Boolean(draftId) && enabled,
    ...DYNAMIC_OPTS,
  })
}

/**
 * Aprovação de rascunho — substitui o horário ativo pelo rascunho.
 */
export const useApproveDraft = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async (draftId) => {
      return apiClient.post(`/scheduler/drafts/${draftId}/approve`)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['scheduler-status', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['scheduler-current-draft', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['schedule-diff', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['weekSchedule', orgId] })
      void invalidatePreparationQueries(queryClient, orgId)
    },
  })
}

/**
 * Rejeição de rascunho — elimina o rascunho sem alterar o ativo.
 */
export const useRejectDraft = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async (draftId) => {
      return apiClient.post(`/scheduler/drafts/${draftId}/reject`)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['scheduler-status', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['scheduler-current-draft', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['schedule-diff', orgId] })
    },
  })
}

/**
 * Disparar geração com estratégia escolhida pelo servidor.
 * Retorna o job persistente, a estratégia e o motivo escolhidos pelo servidor.
 */
export const useGenerateSchedule = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ replacePendingDraft = false } = {}) => {
      return apiClient.post('/scheduler/generate', {
        replace_pending_draft: replacePendingDraft,
      })
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['scheduler-status', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['scheduler-current-draft', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['weekSchedule', orgId] })
    },
  })
}

/**
 * Verificar estado de uma tarefa Celery de geração.
 */
export const useScheduleTaskStatus = (jobId) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['scheduler-job', orgId, jobId],
    queryFn: async () => {
      return apiClient.get(`/scheduler/jobs/${jobId}`)
    },
    enabled: Boolean(orgId) && Boolean(jobId),
    refetchInterval: (query) => {
      if (query.state.error) return false
      const status = query.state.data?.job_status
      if (!status) return 5000
      const terminal = ['SUCCEEDED', 'FAILED', 'CANCELED', 'NO_VALID_OUTPUT']
      return terminal.includes(status) ? false : 5000
    },
    ...DYNAMIC_OPTS,
  })
}

/**
 * Solicita cancelamento de uma tarefa de geração em curso.
 */
export const useCancelScheduleTask = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id
  return useMutation({
    mutationFn: async (jobId) => {
      return apiClient.post(`/scheduler/jobs/${jobId}/cancel`)
    },
    onSuccess: (_data, jobId) => {
      void queryClient.invalidateQueries({ queryKey: ['scheduler-job', orgId, jobId] })
      void queryClient.invalidateQueries({ queryKey: ['scheduler-status', orgId] })
    },
  })
}

/**
 * Sprint 4 — Horário de uma semana para uma turma ou professor.
 *
 * Retorna os blocos publicados cruzados com as ocorrencias reais.
 * Requer classId ou teacherId.
 */
export const useTeacherScheduleHorizon = ({ enabled = true, refetchInterval = false } = {}) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['teacherScheduleHorizon', orgId],
    queryFn: async () => {
      return apiClient.get('/schedule/me/horizon')
    },
    enabled: Boolean(orgId) && enabled,
    refetchInterval,
    refetchIntervalInBackground: Boolean(refetchInterval),
  })
}

export const useWeekSchedule = (classId, teacherId, weekStart) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  const enabled = Boolean(orgId)
    && Boolean(weekStart)
    && (Boolean(classId) !== Boolean(teacherId))
  return useQuery({
    queryKey: ['weekSchedule', orgId, classId, teacherId, weekStart],
    queryFn: async () => {
      const params = { week_start: weekStart }
      if (classId) params.class_id = classId
      if (teacherId) params.teacher_id = teacherId
      return apiClient.get('/schedule/week', { params })
    },
    enabled,
  })
}
