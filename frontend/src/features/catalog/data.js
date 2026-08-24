import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useApiClient } from '../../ApiClientContext'
import { invalidatePreparationQueries } from '../readiness/data'
import { useOrganization, useAuth } from '@clerk/react'

const STATIC_OPTS = {
  staleTime: 1000 * 60 * 30,
  refetchOnWindowFocus: false,
}

export const useRooms = () => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['rooms', orgId],
    queryFn: async () => {
      return apiClient.get('/rooms/')
    },
    enabled: Boolean(orgId),
    ...STATIC_OPTS
  })
}

export const useSubjects = () => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['subjects', orgId],
    queryFn: async () => {
      return apiClient.get('/subjects/')
    },
    enabled: Boolean(orgId),
    ...STATIC_OPTS
  })
}

export const useClasses = ({ enabled = true } = {}) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['classes', orgId],
    queryFn: async () => {
      return apiClient.get('/classes/')
    },
    enabled: Boolean(orgId) && enabled,
    ...STATIC_OPTS
  })
}


export const useTimeslots = () => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  const { isLoaded } = useAuth()
  return useQuery({
    queryKey: ['timeslots', orgId],
    queryFn: async () => {
      return apiClient.get('/timeslots/')
    },
    enabled: Boolean(orgId) && isLoaded,
  })
}

// --- CURSOS ---
export const useCourses = () => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['courses', orgId],
    queryFn: async () => {
      return apiClient.get('/courses/')
    },
    enabled: Boolean(orgId),
    ...STATIC_OPTS
  })
}

// --- CURRÍCULO DA TURMA (Dados Relacionados) ---


// --- HOOKS OPERACIONAIS (Dinâmicos) ---


// ==========================================
//  HOOKS DE MUTAÇÃO GENÉRICOS (CRUD Factory)
//  Estes hooks gerem a escrita e a atualização automática da cache.
// ==========================================

/**
 * Cria uma nova entidade.
 * @param {string} entityKey - O nome da entidade (ex: 'rooms'). Define o URL e a Cache Key.
 */
const useCreateEntity = (entityKey, dependentRoots = []) => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async (newItem) => {
      return apiClient.post(`/${entityKey}/`, newItem)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [entityKey, orgId] })
      dependentRoots.forEach((root) => {
        queryClient.invalidateQueries({ queryKey: [root, orgId] })
      })
      void invalidatePreparationQueries(queryClient, orgId)
    }
  })
}

/**
 * Atualiza uma entidade existente.
 * Uso: mutate({ id: 1, name: "Novo Nome" })
 * 
 * PATCH: Atualização parcial (apenas campos enviados)
 */
const useUpdateEntity = (entityKey, dependentRoots = []) => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ id, ...updateData }) => {
      return apiClient.patch(`/${entityKey}/${id}`, updateData)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [entityKey, orgId] })
      dependentRoots.forEach((root) => {
        queryClient.invalidateQueries({ queryKey: [root, orgId] })
      })
      void invalidatePreparationQueries(queryClient, orgId)
    }
  })
}

/**
 * Apaga uma entidade.
 * Uso: mutate(1)
 */
const useDeleteEntity = (entityKey, dependentRoots = []) => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async (id) => {
      await apiClient.delete(`/${entityKey}/${id}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [entityKey, orgId] })
      dependentRoots.forEach((root) => {
        queryClient.invalidateQueries({ queryKey: [root, orgId] })
      })
      void invalidatePreparationQueries(queryClient, orgId)
    }
  })
}

export const useCreateRoom = () => useCreateEntity('rooms')
export const useUpdateRoom = () => useUpdateEntity('rooms')
export const useDeleteRoom = () => useDeleteEntity('rooms')
export const useCreateSubject = () => useCreateEntity('subjects', ['courses'])
export const useUpdateSubject = () => useUpdateEntity('subjects', ['courses'])
export const useDeleteSubject = () => useDeleteEntity('subjects', ['courses'])
export const useCreateCourse = () => useCreateEntity('courses')
export const useUpdateClass = () => useUpdateEntity('classes')

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
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['courses', orgId, courseId],
    queryFn: async () => {
      return apiClient.get(`/courses/${courseId}`)
    },
    enabled: Boolean(orgId) && Boolean(courseId),
    staleTime: 0,
    refetchOnWindowFocus: true,
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
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ courseId, data }) => {
      return apiClient.patch(`/courses/${courseId}`, data)
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
  const apiClient = useApiClient()
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
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ courseId, data }) => {
      return apiClient.post(`/courses/${courseId}/classes`, data)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['courses', orgId] })
      queryClient.invalidateQueries({ queryKey: ['courses', orgId, variables.courseId] })
      queryClient.invalidateQueries({ queryKey: ['classes', orgId] })
    }
  })
}


export const useUpdateCourseClass = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ courseId, classId, data }) => {
      return apiClient.patch(`/courses/${courseId}/classes/${classId}`, data)
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
  const apiClient = useApiClient()
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
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['classes', orgId, classId],
    queryFn: async () => {
      return apiClient.get(`/classes/${classId}`)
    },
    enabled: Boolean(orgId) && Boolean(classId),
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
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ classId, progress }) => {
      return apiClient.patch(`/classes/${classId}/progress`, { progress })
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
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['class-subjects', orgId, classId],
    queryFn: async () => {
      if (!classId) return null
      return apiClient.get(`/classes/${classId}/subjects`)
    },
    enabled: Boolean(orgId) && Boolean(classId),
    staleTime: 1000 * 60 * 5,
    refetchOnWindowFocus: false,
  })
}

/**
 * Lista disciplinas disponíveis para adicionar à turma.
 * (Disciplinas da org que ainda não estão associadas)
 */
export const useAvailableSubjects = (classId) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['available-subjects', orgId, classId],
    queryFn: async () => {
      if (!classId) return []
      return apiClient.get(`/classes/${classId}/available-subjects`)
    },
    enabled: Boolean(orgId) && Boolean(classId),
    staleTime: 1000 * 60 * 5,
  })
}

/**
 * Lista professores elegíveis para lecionar uma disciplina.
 * (Professores que têm competência na disciplina)
 */
export const useEligibleTeachers = (subjectId) => {
  const apiClient = useApiClient()
  const orgId = useOrganization().organization?.id
  return useQuery({
    queryKey: ['eligible-teachers', orgId, subjectId],
    queryFn: async () => {
      if (!subjectId) return []
      return apiClient.get(`/classes/subjects/${subjectId}/eligible-teachers`)
    },
    enabled: Boolean(orgId) && Boolean(subjectId),
    staleTime: 1000 * 60 * 5,
  })
}

/**
 * Adiciona uma disciplina à turma.
 */
export const useAddClassSubject = () => {
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ classId, subjectId }) => {
      return apiClient.post(`/classes/${classId}/subjects`, { subject_id: subjectId })
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
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ classId, subjectId, teacherId }) => {
      const payload = {}
      if (teacherId !== undefined) payload.teacher_id = teacherId
      return apiClient.patch(`/classes/${classId}/subjects/${subjectId}`, payload)
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
  const apiClient = useApiClient()
  const queryClient = useQueryClient()
  const orgId = useOrganization().organization?.id

  return useMutation({
    mutationFn: async ({ classId, subjectId }) => {
      return apiClient.delete(`/classes/${classId}/subjects/${subjectId}`)
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
