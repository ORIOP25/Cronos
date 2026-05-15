import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../apiClient'
import { useOrganization, useAuth } from '@clerk/react'

/**
 * CONFIGURAÇÃO DE CACHE (A "Magia" da Performance)
 * * STATIC_OPTS: Para dados que mudam raramente (Metadados).
 * - Cache de 30 minutos.
 * - Não recarrega quando mudas de janela.
 * * DYNAMIC_OPTS: Para dados operacionais (Horários, Substituições).
 * - Cache de 5 minutos (ou menos, se preferires).
 * - Mantemos refetchOnWindowFocus para garantir que o utilizador vê dados frescos se voltar à tab.
 */
const STATIC_OPTS = {
  staleTime: 1000 * 60 * 30,
  refetchOnWindowFocus: false,
  refetchOnMount: true,
  retry: 3
}

const DYNAMIC_OPTS = {
  staleTime: 1000 * 60 * 5, // 5 minutos de "frescura"
  refetchOnWindowFocus: true,
  retry: 2
}

// --- HOOKS DE LEITURA (Read) ---

export const useTeachers = ({ enabled = true } = {}) => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['teachers', orgId],
    queryFn: async () => {
      const { data } = await apiClient.get('/import/teachers')
      return data
    },
    enabled: Boolean(orgId) && enabled,
    ...STATIC_OPTS
  })
}

export const useRooms = () => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['rooms', orgId],
    queryFn: async () => {
      const { data } = await apiClient.get('/import/rooms')
      return data
    },
    enabled: Boolean(orgId),
    ...STATIC_OPTS
  })
}

export const useSubjects = () => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['subjects', orgId],
    queryFn: async () => {
      const { data } = await apiClient.get('/import/subjects')
      return data
    },
    enabled: Boolean(orgId),
    ...STATIC_OPTS
  })
}

export const useClasses = ({ enabled = true } = {}) => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['classes', orgId],
    queryFn: async () => {
      const { data } = await apiClient.get('/classes/')
      return data
    },
    enabled: Boolean(orgId) && enabled,
    ...STATIC_OPTS
  })
}

export const useLessons = () => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['lessons', orgId],
    queryFn: async () => {
      const { data } = await apiClient.get('/import/lessons')
      return data
    },
    enabled: Boolean(orgId),
    ...STATIC_OPTS
  })
}

export const useTimeslots = () => {
  const orgId = useOrganization().organization?.id
  const { isLoaded } = useAuth()
  return useQuery({
    queryKey: ['timeslots', orgId],
    queryFn: async () => {
      const { data } = await apiClient.get('/timeslots/')
      return data
    },
    enabled: Boolean(orgId) && isLoaded,
    staleTime: 0,
    refetchOnWindowFocus: true,
    refetchOnMount: true,
    retry: 1,
  })
}

// --- CURSOS ---
export const useCourses = () => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['courses', orgId],
    queryFn: async () => {
      const { data } = await apiClient.get('/courses/')
      return data
    },
    ...STATIC_OPTS
  })
}

// --- CURRÍCULO DA TURMA (Dados Relacionados) ---
/**
 * Hook para carregar o currículo (disciplinas) de uma turma.
 * 
 * Implementa o padrão de "Dados Relacionados":
 * - enabled=!!classId: Só faz fetch se classId existir
 * - queryKey inclui classId: Cache separada por turma
 * - STATIC_OPTS: Currículo muda raramente
 * 
 * Uso:
 * const { data: curriculum, isLoading } = useClassCurriculum(5)
 */
export const useClassCurriculum = (classId) => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['class-curriculum', orgId, classId],
    queryFn: async () => {
      if (!classId) return []
      const { data } = await apiClient.get(`/classes/${classId}/curriculum`)
      return data
    },
    enabled: !!classId,
    ...STATIC_OPTS
  })
}

// --- HOOKS OPERACIONAIS (Dinâmicos) ---

export const useSchedule = () => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['schedule', orgId],
    queryFn: async () => {
      const { data } = await apiClient.get('/schedule/latest')
      return data
    },
    ...DYNAMIC_OPTS
  })
}

export const useSubstitutions = () => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['substitutions', orgId],
    queryFn: async () => {
      const { data } = await apiClient.get('/substitutions/')
      return data
    },
    staleTime: 1000 * 60,
    refetchOnWindowFocus: true
  })
}

// ==========================================
//  HOOKS DE MUTAÇÃO GENÉRICOS (CRUD Factory)
//  Estes hooks gerem a escrita e a atualização automática da cache.
// ==========================================

/**
 * Cria uma nova entidade.
 * @param {string} entityKey - O nome da entidade (ex: 'teachers'). Define o URL (/teachers/) e a Cache Key.
 */
export const useCreateEntity = (entityKey) => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async (newItem) => {
      const { data } = await apiClient.post(`/${entityKey}/`, newItem)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [entityKey, orgId] })
    }
  })
}

/**
 * Atualiza uma entidade existente.
 * Uso: mutate({ id: 1, name: "Novo Nome" })
 * 
 * PATCH: Atualização parcial (apenas campos enviados)
 */
export const useUpdateEntity = (entityKey) => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ id, ...updateData }) => {
      const { data } = await apiClient.patch(`/${entityKey}/${id}`, updateData)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [entityKey, orgId] })
    }
  })
}

/**
 * Apaga uma entidade.
 * Uso: mutate(1)
 */
export const useDeleteEntity = (entityKey) => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async (id) => {
      await apiClient.delete(`/${entityKey}/${id}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [entityKey, orgId] })
    }
  })
}

// ==========================================
//  FASE 4: GESTÃO DE CURSOS
//  Hooks específicos para operações de cursos com hierarchia (Course → Class)
// ==========================================

/**
 * Obter detalhes completos de um curso (Dashboard).
 * 
 * 4º Pilares:
 * - Optimization: Cache separada por courseId, staleTime 5min (dados semi-estáticos)
 * - Scalability: enabled flag previne queries desnecessárias
 * - Stability: Retorna subjects + classes de uma vez (évita N+1)
 * 
 * Uso:
 * const { data: course, isLoading } = useCourseDetails(5)
 * course.subjects[0].name
 * course.classes[0].name
 */
export const useCourseDetails = (courseId) => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['courses', orgId, courseId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/courses/${courseId}`)
      return data
    },
    enabled: !!courseId,
    staleTime: 0,
    refetchOnWindowFocus: true,
  })
}

/**
 * Criar novo curso com turmas automáticas.
 * 
 * 4º Pilares:
 * - Security: Backend valida abbreviation uniqueness
 * - Stability: onSuccess invalida caches para garantir consistência
 * 
 * Uso:
 * const createCourse = useCreateCourse()
 * createCourse.mutate({
 *   name: "Técnico em Informática",
 *   abbreviation: "TI",
 *   subject_ids: [1, 2],
 *   classes_config: [
 *     { grade_level: 10, size: 25, start_year: 2025, end_year: 2028 }
 *   ]
 * })
 */
export const useCreateCourse = () => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async (newCourse) => {
      const { data } = await apiClient.post('/courses/', newCourse)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['courses', orgId] })
    }
  })
}

/**
 * Atualizar curso (PATCH - apenas campos enviados).
 * 
 * 4º Pilares:
 * - Security: Backend valida abbreviation uniqueness
 * - Stability: PATCH permite atualizações parciais sem risco de sobrescrever
 * - Optimization: Invalida caches específicas (listagem + detalhe)
 * 
 * Uso:
 * const updateCourse = useUpdateCourse()
 * updateCourse.mutate({
 *   courseId: 5,
 *   data: { name: "Novo Nome", subject_ids: [1, 2, 3] }
 * })
 */
export const useUpdateCourse = () => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ courseId, data }) => {
      const { data: response } = await apiClient.patch(`/courses/${courseId}`, data)
      return response
    },
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['courses', orgId] })
      queryClient.invalidateQueries({ queryKey: ['courses', orgId, variables.courseId] })
    }
  })
}

/**
 * Apagar curso com validação de dependências.
 * 
 * 4º Pilares:
 * - Stability: Backend rejeita se há classes (impede perda de dados)
 * - Security: Validação no servidor, frontend apenas consome resposta
 * 
 * Uso:
 * const deleteCourse = useDeleteCourse()
 * deleteCourse.mutate(5) // courseId
 */
export const useDeleteCourse = () => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async (courseId) => {
      await apiClient.delete(`/courses/${courseId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['courses', orgId] })
    }
  })
}


export const useCreateCourseClass = () => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ courseId, data }) => {
      const { data: response } = await apiClient.post(`/courses/${courseId}/classes`, data)
      return response
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['courses', orgId] })
      queryClient.invalidateQueries({ queryKey: ['courses', orgId, variables.courseId] })
      queryClient.invalidateQueries({ queryKey: ['classes', orgId] })
    }
  })
}


export const useUpdateCourseClass = () => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ courseId, classId, data }) => {
      const { data: response } = await apiClient.patch(`/courses/${courseId}/classes/${classId}`, data)
      return response
    },
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['courses', orgId] })
      queryClient.invalidateQueries({ queryKey: ['courses', orgId, variables.courseId] })
      queryClient.invalidateQueries({ queryKey: ['classes', orgId] })
      queryClient.setQueryData(['classes', orgId, variables.classId], (previous) => (
        previous ? { ...previous, ...data } : previous
      ))
    }
  })
}


export const useDeleteCourseClass = () => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ courseId, classId }) => {
      await apiClient.delete(`/courses/${courseId}/classes/${classId}`)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['courses', orgId] })
      queryClient.invalidateQueries({ queryKey: ['courses', orgId, variables.courseId] })
      queryClient.invalidateQueries({ queryKey: ['classes', orgId] })
      queryClient.removeQueries({ queryKey: ['classes', orgId, variables.classId] })
      queryClient.removeQueries({ queryKey: ['class-subjects', orgId, variables.classId] })
      queryClient.removeQueries({ queryKey: ['available-subjects', orgId, variables.classId] })
    }
  })
}

// ==========================================
//  FASE 4: GESTÃO DE TURMAS (Esqueleto)
//  Implementação completa na Fase 5
// ==========================================

/**
 * Obter dashboard completo de uma turma.
 * 
 * Retorna: ClassFullDetailRead
 * - Dados da turma (nome, capacidade, grade_level, start_year, end_year)
 * - Curso associado (nome, sigla)
 * - Disciplinas com módulos e progresso (horas, percentagem, is_completed)
 * 
 * 4 Pilares:
 * - Scalability: Cache separada por classId
 * - Stability: enabled flag previne queries desnecessárias
 * - Optimization: Backend retorna tudo em 2 queries (vs N+1)
 */
export const useClassDetails = (classId) => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['classes', orgId, classId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/classes/${classId}`)
      return data
    },
    enabled: !!classId,
    staleTime: 0,
    refetchOnWindowFocus: true,
  })
}

/**
 * Atualizar progresso de módulos de uma turma.
 * 
 * Uso:
 * const updateProgress = useUpdateClassProgress()
 * updateProgress.mutate({
 *   classId: 5,
 *   progress: [
 *     { module_id: 1, hours_completed: 25 },
 *     { module_id: 2, hours_completed: 50 }
 *   ]
 * })
 * 
 * 4 Pilares:
 * - Stability: Invalida cache da turma + lista para garantir consistência
 * - Security: Backend valida que módulos pertencem ao curso da turma
 */
export const useUpdateClassProgress = () => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ classId, progress }) => {
      const { data } = await apiClient.patch(`/classes/${classId}/progress`, { progress })
      return data
    },
    onSuccess: (data, variables) => {
      queryClient.setQueryData(['classes', orgId, variables.classId], data)
      queryClient.invalidateQueries({ queryKey: ['classes', orgId] })
    }
  })
}

// ==========================================
//  DISCIPLINAS DA TURMA (Class-Subject Link)
//  Gestão curso-cêntrica de professores
// ==========================================

/**
 * Lista disciplinas associadas à turma (para o grade_level atual).
 * Inclui professor atribuído a cada disciplina.
 * 
 * Usado na página ClassSubjects.jsx
 */
export const useClassSubjects = (classId) => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['class-subjects', orgId, classId],
    queryFn: async () => {
      if (!classId) return null
      const { data } = await apiClient.get(`/classes/${classId}/subjects`)
      return data
    },
    enabled: !!classId,
    staleTime: 1000 * 60 * 5,
    refetchOnWindowFocus: false,
  })
}

/**
 * Lista disciplinas disponíveis para adicionar à turma.
 * (Disciplinas da org que ainda não estão associadas)
 */
export const useAvailableSubjects = (classId) => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['available-subjects', orgId, classId],
    queryFn: async () => {
      if (!classId) return []
      const { data } = await apiClient.get(`/classes/${classId}/available-subjects`)
      return data
    },
    enabled: !!classId,
    staleTime: 1000 * 60 * 5,
  })
}

/**
 * Lista professores elegíveis para lecionar uma disciplina.
 * (Professores que têm competência na disciplina)
 */
export const useEligibleTeachers = (subjectId) => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['eligible-teachers', orgId, subjectId],
    queryFn: async () => {
      if (!subjectId) return []
      const { data } = await apiClient.get(`/classes/subjects/${subjectId}/eligible-teachers`)
      return data
    },
    enabled: !!subjectId,
    staleTime: 1000 * 60 * 5,
  })
}

/**
 * Adiciona uma disciplina à turma.
 */
export const useAddClassSubject = () => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ classId, subjectId }) => {
      const { data } = await apiClient.post(`/classes/${classId}/subjects`, { subject_id: subjectId })
      return data
    },
    onSuccess: (data, variables) => {
      queryClient.setQueryData(['class-subjects', orgId, variables.classId], data)
      queryClient.invalidateQueries({ queryKey: ['available-subjects', orgId, variables.classId] })
      queryClient.invalidateQueries({ queryKey: ['classes', orgId, variables.classId] })
      queryClient.invalidateQueries({ queryKey: ['courses', orgId] })
    }
  })
}

/**
 * Atualiza o professor de uma disciplina da turma.
 */
export const useUpdateClassSubjectTeacher = () => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ classId, subjectId, teacherId }) => {
      const payload = {}
      if (teacherId !== undefined) payload.teacher_id = teacherId
      const { data } = await apiClient.patch(`/classes/${classId}/subjects/${subjectId}`, payload)
      return data
    },
    onSuccess: (data, variables) => {
      queryClient.setQueryData(['class-subjects', orgId, variables.classId], data)
    }
  })
}

/**
 * Remove uma disciplina da turma.
 */
export const useRemoveClassSubject = () => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ classId, subjectId }) => {
      const { data } = await apiClient.delete(`/classes/${classId}/subjects/${subjectId}`)
      return data
    },
    onSuccess: (data, variables) => {
      queryClient.setQueryData(['class-subjects', orgId, variables.classId], data)
      queryClient.invalidateQueries({ queryKey: ['available-subjects', orgId, variables.classId] })
      queryClient.invalidateQueries({ queryKey: ['classes', orgId, variables.classId] })
      queryClient.invalidateQueries({ queryKey: ['courses', orgId] })
    }
  })
}

// ==========================================
//  SPRINT 2 — OCORRÊNCIAS & DÍVIDAS
// ==========================================

/**
 * Lista ocorrências com filtros opcionais (classId, dateFrom, dateTo).
 */
export const useOccurrences = ({ classId, dateFrom, dateTo } = {}) => {
  const orgId = useOrganization().organization?.id
  const params = new URLSearchParams()
  if (classId) params.set('class_id', classId)
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  const qs = params.toString()
  const endpoint = qs ? `/occurrences/?${qs}` : '/occurrences/'

  return useQuery({
    queryKey: ['occurrences', orgId, classId, dateFrom, dateTo],
    queryFn: async () => {
      const { data } = await apiClient.get(endpoint)
      return data
    },
    ...DYNAMIC_OPTS,
  })
}

/**
 * Lista de dívidas de horas agrupadas por turma/disciplina.
 */
export const useDebts = ({ classId } = {}) => {
  const orgId = useOrganization().organization?.id
  const params = new URLSearchParams()
  if (classId) params.set('class_id', classId)
  const qs = params.toString()
  const endpoint = qs ? `/occurrences/debts?${qs}` : '/occurrences/debts'

  return useQuery({
    queryKey: ['debts', orgId, classId],
    queryFn: async () => {
      const { data } = await apiClient.get(endpoint)
      return data
    },
    ...DYNAMIC_OPTS,
  })
}

/**
 * Professores disponíveis para substitição num slot/data específicos.
 */
export const useAvailableSubstitutes = ({ timeslotId, targetDate } = {}) => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['substitutes', orgId, timeslotId, targetDate],
    queryFn: async () => {
      const { data } = await apiClient.get('/occurrences/substitutes', {
        params: { timeslot_id: timeslotId, target_date: targetDate },
      })
      return data
    },
    enabled: !!(timeslotId && targetDate),
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
      const { data } = await apiClient.get(`/occurrences/${occurrenceId}/substitutes/recommendations`)
      return data
    },
    enabled: !!occurrenceId,
    ...DYNAMIC_OPTS,
  })
}

/**
 * Cria (ou reutiliza) uma ocorrência operacional a partir de um bloco do horário.
 */
export const useCreateOccurrence = () => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ scheduleOutputId, reason } = {}) => {
      const payload = {
        schedule_output_id: scheduleOutputId,
      }
      if (reason) {
        payload.reason = reason
      }
      const { data } = await apiClient.post('/occurrences/', payload)
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['occurrences', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['weekSchedule', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['schedule', orgId] })
    },
  })
}

/**
 * Mutation para registar falta (GAP) ou substituição (SUBSTITUTED).
 */
export const useUpdateOccurrence = () => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ id, status, substituteTeacherId, substituteSubjectId }) => {
      const { data } = await apiClient.patch(`/occurrences/${id}`, {
        status,
        substitute_teacher_id: substituteTeacherId ?? null,
        substitute_subject_id: substituteSubjectId ?? null,
      })
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['occurrences', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['debts', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['weekSchedule', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['classes', orgId] })
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
    mutationFn: async (id) => {
      const { data } = await apiClient.post(`/occurrences/${id}/cancel`)
      return data
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
    mutationFn: async ({ scheduleOutputId, payload }) => {
      const { data } = await apiClient.put(`/schedule/outputs/${scheduleOutputId}/log`, payload)
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['weekSchedule', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['classes', orgId] })
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
      const { data } = await apiClient.get(`/timesheets/me/${weekStartDate}`)
      return data
    },
    enabled: !!weekStartDate,
    ...DYNAMIC_OPTS,
  })
}

export const useSubmitMyTimesheet = () => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async (weekStartDate) => {
      const { data } = await apiClient.post(`/timesheets/me/${weekStartDate}/submit`)
      return data
    },
    onSuccess: (_, weekStartDate) => {
      void queryClient.invalidateQueries({ queryKey: ['my-timesheet', orgId, weekStartDate] })
      void queryClient.invalidateQueries({ queryKey: ['weekSchedule', orgId] })
    },
  })
}

export const useTimesheets = (weekStartDate, status) => {
  const orgId = useOrganization().organization?.id
  const params = new URLSearchParams()
  if (weekStartDate) params.set('week_start_date', weekStartDate)
  if (status) params.set('status', status)
  const qs = params.toString()
  const endpoint = qs ? `/timesheets/?${qs}` : '/timesheets/'

  return useQuery({
    queryKey: ['timesheets', orgId, weekStartDate, status],
    queryFn: async () => {
      const { data } = await apiClient.get(endpoint)
      return data
    },
    ...DYNAMIC_OPTS,
  })
}

export const useUpdateTimesheetStatus = () => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ timesheetId, status }) => {
      const { data } = await apiClient.patch(`/timesheets/${timesheetId}/status`, { status })
      return data
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
export const useDrafts = () => {
  const orgId = useOrganization().organization?.id
  const { isLoaded } = useAuth()
  return useQuery({
    queryKey: ['drafts', orgId],
    queryFn: async () => {
      const { data } = await apiClient.get('/schedule/drafts')
      return data
    },
    enabled: Boolean(orgId) && isLoaded,
    ...DYNAMIC_OPTS,
  })
}

/**
 * Diff entre um rascunho e o horário ativo.
 */
export const useScheduleDiff = (genId) => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['schedule-diff', orgId, genId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/schedule/drafts/${genId}/diff`)
      return data
    },
    enabled: !!genId,
    ...DYNAMIC_OPTS,
  })
}

/**
 * Aprovação de rascunho — substitui o horário ativo pelo rascunho.
 */
export const useApproveDraft = () => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async (genId) => {
      const { data } = await apiClient.post(`/schedule/drafts/${genId}/approve`)
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['drafts', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['schedule-diff', orgId] })
    },
  })
}

/**
 * Rejeição de rascunho — elimina o rascunho sem alterar o ativo.
 */
export const useRejectDraft = () => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async (genId) => {
      const { data } = await apiClient.delete(`/schedule/drafts/${genId}`)
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['drafts', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['schedule-diff', orgId] })
    },
  })
}

/**
 * Disparar geração de horário (full ou repair).
 * Retorna { task_id, status }.
 */
export const useGenerateSchedule = () => {
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async (mode = 'full') => {
      const { data } = await apiClient.post('/schedule/generate', { mode })
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['drafts', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['weekSchedule', orgId] })
      void queryClient.invalidateQueries({ queryKey: ['schedule', orgId] })
    },
  })
}

/**
 * Verificar estado de uma tarefa Celery de geração.
 */
export const useScheduleTaskStatus = (taskId) => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['schedule-task', orgId, taskId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/schedule/status/${taskId}`)
      return data
    },
    enabled: !!taskId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (!status) return 5000
      const terminal = ['SUCCESS', 'FAILURE', 'Success', 'Error', 'Impossible']
      return terminal.some(s => status.includes(s)) ? 60000 : 5000
    },
    ...DYNAMIC_OPTS,
  })
}

/**
 * Solicita cancelamento de uma tarefa de geração em curso.
 */
export const useCancelScheduleTask = () => {
  return useMutation({
    mutationFn: async (taskId) => {
      const { data } = await apiClient.post(`/schedule/cancel/${taskId}`)
      return data
    },
  })
}

/**
 * Sprint 4 — Horário de uma semana para uma turma ou professor.
 *
 * Retorna os slots planeados (ScheduleOutput) cruzados com as ocorrências reais
 * (LessonOccurrence) para dias passados. Requer classId ou teacherId.
 */
export const useTeacherScheduleHorizon = ({ enabled = true, refetchInterval = false } = {}) => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['teacherScheduleHorizon', orgId],
    queryFn: async () => {
      const { data } = await apiClient.get('/schedule/me/horizon')
      return data
    },
    enabled,
    refetchInterval,
    refetchIntervalInBackground: Boolean(refetchInterval),
    staleTime: 0,
    refetchOnWindowFocus: true,
    refetchOnMount: true,
    retry: 1,
  })
}

export const useWeekSchedule = (classId, teacherId, weekStart) => {
  const orgId = useOrganization().organization?.id
  const enabled = Boolean((classId || teacherId) && weekStart)
  return useQuery({
    queryKey: ['weekSchedule', orgId, classId, teacherId, weekStart],
    queryFn: async () => {
      const params = { week_start: weekStart }
      if (classId) params.class_id = classId
      if (teacherId) params.teacher_id = teacherId
      const { data } = await apiClient.get('/schedule/week', { params })
      return data
    },
    enabled,
    staleTime: 0,
    refetchOnWindowFocus: true,
    refetchOnMount: true,
    retry: 1,
  })
}

/**
 * Dashboard técnico — lista gerações disponíveis para auditoria.
 */
export const useAuditGenerations = () => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['schedule-audit-generations', orgId],
    queryFn: async () => {
      const { data } = await apiClient.get('/schedule/audit/generations')
      return data
    },
    ...DYNAMIC_OPTS,
  })
}

/**
 * Dashboard técnico — métricas de auditoria por geração.
 */
export const useAuditSummary = (generationId, { enabled = true } = {}) => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['schedule-audit-summary', orgId, generationId],
    queryFn: async () => {
      const params = generationId ? { generation_id: generationId } : {}
      const { data } = await apiClient.get('/schedule/audit/summary', { params })
      return data
    },
    enabled,
    ...DYNAMIC_OPTS,
  })
}

/**
 * Dashboard V1 — Command Center. Agrega alertas, saúde do horário,
 * progresso curricular, contagens de recursos e resumo de dívidas.
 */
export const useDashboard = ({ enabled = true } = {}) => {
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['dashboard', orgId],
    queryFn: async () => {
      const { data } = await apiClient.get('/dashboard')
      return data
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
      const { data } = await apiClient.get('/teachers/me/progress')
      return data
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
      const { data } = await apiClient.get('/teachers/me/availability')
      return data
    },
    enabled: Boolean(orgId) && isLoaded && enabled,
    staleTime: 0,
    refetchOnWindowFocus: true,
    refetchOnMount: true,
    retry: 1,
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
      const { data } = await apiClient.post(`/teachers/${teacherId}/availability`, payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-availability', orgId] })
    },
  })
}
