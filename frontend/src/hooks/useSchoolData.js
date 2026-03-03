import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../apiClient'
import { useAuthStore } from '../store'

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
  staleTime: 1000 * 60 * 30, // 30 minutos sem pedir ao servidor
  refetchOnWindowFocus: false,
  refetchOnMount: false, // Se o componente desmontar e montar, usa a cache
  retry: 1
}

const DYNAMIC_OPTS = {
  staleTime: 1000 * 60 * 5, // 5 minutos de "frescura"
  refetchOnWindowFocus: true,
  retry: 2
}

// --- HOOKS DE LEITURA (Read) ---

export const useTeachers = () => {
  const orgId = useAuthStore(state => state.user?.orgId)
  return useQuery({
    queryKey: ['teachers', orgId],
    queryFn: async () => {
      const { data } = await apiClient.get('/import/teachers')
      return data
    },
    ...STATIC_OPTS
  })
}

export const useRooms = () => {
  const orgId = useAuthStore(state => state.user?.orgId)
  return useQuery({
    queryKey: ['rooms', orgId],
    queryFn: async () => {
      const { data } = await apiClient.get('/import/rooms')
      return data
    },
    ...STATIC_OPTS
  })
}

export const useSubjects = () => {
  const orgId = useAuthStore(state => state.user?.orgId)
  return useQuery({
    queryKey: ['subjects', orgId],
    queryFn: async () => {
      const { data } = await apiClient.get('/import/subjects')
      return data
    },
    ...STATIC_OPTS
  })
}

export const useClasses = () => {
  const orgId = useAuthStore(state => state.user?.orgId)
  return useQuery({
    queryKey: ['classes', orgId],
    queryFn: async () => {
      const { data } = await apiClient.get('/classes/')
      return data
    },
    ...STATIC_OPTS
  })
}

export const useLessons = () => {
  const orgId = useAuthStore(state => state.user?.orgId)
  return useQuery({
    queryKey: ['lessons', orgId],
    queryFn: async () => {
      const { data } = await apiClient.get('/import/lessons')
      return data
    },
    ...STATIC_OPTS
  })
}

export const useTimeslots = () => {
  const orgId = useAuthStore(state => state.user?.orgId)
  return useQuery({
    queryKey: ['timeslots', orgId],
    queryFn: async () => {
      const { data } = await apiClient.get('/timeslots/')
      return data
    },
    ...STATIC_OPTS
  })
}

// --- CURSOS ---
export const useCourses = () => {
  const orgId = useAuthStore(state => state.user?.orgId)
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
  const orgId = useAuthStore(state => state.user?.orgId)
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
  const orgId = useAuthStore(state => state.user?.orgId)
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
  const orgId = useAuthStore(state => state.user?.orgId)
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
  const orgId = useAuthStore(state => state.user?.orgId)

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
  const orgId = useAuthStore(state => state.user?.orgId)

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
  const orgId = useAuthStore(state => state.user?.orgId)

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
  const orgId = useAuthStore(state => state.user?.orgId)
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
  const orgId = useAuthStore(state => state.user?.orgId)

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
  const orgId = useAuthStore(state => state.user?.orgId)

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
  const orgId = useAuthStore(state => state.user?.orgId)

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
  const orgId = useAuthStore(state => state.user?.orgId)

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
  const orgId = useAuthStore(state => state.user?.orgId)

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
  const orgId = useAuthStore(state => state.user?.orgId)

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
  const orgId = useAuthStore(state => state.user?.orgId)
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
  const orgId = useAuthStore(state => state.user?.orgId)

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
  const orgId = useAuthStore(state => state.user?.orgId)
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
  const orgId = useAuthStore(state => state.user?.orgId)
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
  const orgId = useAuthStore(state => state.user?.orgId)
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
  const orgId = useAuthStore(state => state.user?.orgId)

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
  const orgId = useAuthStore(state => state.user?.orgId)

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
  const orgId = useAuthStore(state => state.user?.orgId)

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
  const orgId = useAuthStore(state => state.user?.orgId)
  const params = new URLSearchParams()
  if (classId) params.set('class_id', classId)
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  const qs = params.toString()

  return useQuery({
    queryKey: ['occurrences', orgId, classId, dateFrom, dateTo],
    queryFn: async () => {
      const { data } = await apiClient.get(`/occurrences/${qs ? `?${qs}` : ''}`)
      return data
    },
    ...DYNAMIC_OPTS,
  })
}

/**
 * Lista de dívidas de horas agrupadas por turma/disciplina.
 */
export const useDebts = ({ classId } = {}) => {
  const orgId = useAuthStore(state => state.user?.orgId)
  const params = new URLSearchParams()
  if (classId) params.set('class_id', classId)
  const qs = params.toString()

  return useQuery({
    queryKey: ['debts', orgId, classId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/occurrences/debts${qs ? `?${qs}` : ''}`)
      return data
    },
    ...DYNAMIC_OPTS,
  })
}

/**
 * Professores disponíveis para substitição num slot/data específicos.
 */
export const useAvailableSubstitutes = ({ timeslotId, targetDate } = {}) => {
  const orgId = useAuthStore(state => state.user?.orgId)
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
 * Mutation para registar falta (GAP) ou substituição (SUBSTITUTED).
 */
export const useUpdateOccurrence = () => {
  const queryClient = useQueryClient()
  const orgId = useAuthStore(state => state.user?.orgId)

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
  const orgId = useAuthStore(state => state.user?.orgId)
  return useQuery({
    queryKey: ['drafts', orgId],
    queryFn: async () => {
      const { data } = await apiClient.get('/schedule/drafts')
      return data
    },
    ...DYNAMIC_OPTS,
  })
}

/**
 * Diff entre um rascunho e o horário ativo.
 */
export const useScheduleDiff = (genId) => {
  const orgId = useAuthStore(state => state.user?.orgId)
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
  const orgId = useAuthStore(state => state.user?.orgId)

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
  const orgId = useAuthStore(state => state.user?.orgId)

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
  const orgId = useAuthStore(state => state.user?.orgId)

  return useMutation({
    mutationFn: async (mode = 'full') => {
      const { data } = await apiClient.post('/schedule/generate', { mode })
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['drafts', orgId] })
    },
  })
}

/**
 * Verificar estado de uma tarefa Celery de geração.
 */
export const useScheduleTaskStatus = (taskId) => {
  const orgId = useAuthStore(state => state.user?.orgId)
  return useQuery({
    queryKey: ['schedule-task', orgId, taskId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/schedule/status/${taskId}`)
      return data
    },
    enabled: !!taskId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (!status) return 3000
      const terminal = ['SUCCESS', 'FAILURE', 'Success', 'Error', 'Impossible']
      return terminal.some(s => status.includes(s)) ? false : 3000
    },
    ...DYNAMIC_OPTS,
  })
}
